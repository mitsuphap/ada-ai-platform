# app/auto_generator.py
import os
from typing import Dict, List, Type, Any, Optional, Set, Callable
from sqlalchemy import MetaData, Table, Column, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from pydantic import BaseModel, create_model, Field, ConfigDict
from app.db import get_db
from slowapi import Limiter 
from slowapi.util import get_remote_address
import re

# Create limiter instance
limiter = Limiter(key_func=get_remote_address)

# Authentication configuration
def _get_auth_mode() -> str:
    """Get authentication mode from environment variable.
    
    Options:
    - 'none': No authentication required
    - 'write': GET endpoints are public, write operations (POST/PUT/DELETE) require auth
    - 'full': All endpoints require authentication
    
    Default: 'write' (recommended for production)
    """
    return os.getenv("AUTO_API_AUTH_MODE", "write").lower()

def _get_api_key() -> Optional[str]:
    """Get API key from environment variable.
    Falls back to ADMIN_TOKEN if AUTO_API_KEY is not set."""
    return os.getenv("AUTO_API_KEY") or os.getenv("ADMIN_TOKEN")

def _require_auth(x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Authentication dependency that validates API key."""
    expected_key = _get_api_key()
    if not expected_key:
        # If no key is configured, allow access (for development)
        return True
    
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Please provide a valid x-api-key header."
        )
    return True

def _get_auth_dependency(require_auth: bool = False):
    """Get authentication dependency based on configuration.
    
    Args:
        require_auth: If True, authentication is required regardless of mode
    
    Returns:
        Depends object if auth is required, or a no-op dependency otherwise
    """
    auth_mode = _get_auth_mode()
    
    if auth_mode == "none":
        # Return a no-op dependency that always returns True
        def _no_auth():
            return True
        return Depends(_no_auth)
    
    if require_auth or auth_mode == "full":
        return Depends(_require_auth)
    
    # For "write" mode on read operations, no auth required
    def _no_auth():
        return True
    return Depends(_no_auth)

# Base model class that allows extra fields for dynamic schema evolution
# This allows Pydantic to accept fields from database that weren't in the schema at generation time
try:
    # Pydantic v2
    class DynamicBaseModel(BaseModel):
        """Base model that allows extra fields to handle database schema changes"""
        model_config = ConfigDict(extra='allow')
except (TypeError, AttributeError):
    # Pydantic v1 fallback
    class DynamicBaseModel(BaseModel):
        """Base model that allows extra fields to handle database schema changes"""
        class Config:
            extra = 'allow'
class DatabaseIntrospector:
    def __init__(self, db_session: Session):
        self.db = db_session
        # Force fresh inspector from the engine (not cached)
        self.inspector = inspect(db_session.bind)
        # Create fresh metadata and force clear any cached state
        self.metadata = MetaData()
        # Clear any existing metadata first, then reflect fresh schema
        self.metadata.clear()
        
        # Check if database is SQLite (doesn't support schemas)
        is_sqlite = 'sqlite' in str(db_session.bind.url).lower()
        
        if is_sqlite:
            # SQLite doesn't support schemas - reflect without schema
            self.metadata.reflect(bind=db_session.bind, only=None)
        else:
            # PostgreSQL and other databases - use schema
            self.metadata.reflect(bind=db_session.bind, schema="core", only=None)
    
    def get_tables_in_schema(self, schema_name: str = "core") -> List[str]:
        """Get all table names in a specific schema"""
        # Check if database is SQLite (doesn't support schemas)
        is_sqlite = 'sqlite' in str(self.db.bind.url).lower()
        
        if is_sqlite:
            # SQLite doesn't support schemas - get all tables
            return self.inspector.get_table_names()
        else:
            # PostgreSQL and other databases - use schema
            return self.inspector.get_table_names(schema=schema_name)
    
    def get_table_info(self, table_name: str, schema_name: str = "core") -> Dict:
        """Get detailed information about a table - always fresh from database"""
        # Check if database is SQLite (doesn't support schemas)
        is_sqlite = 'sqlite' in str(self.db.bind.url).lower()
        
        # Force fresh introspection from database (not cached)
        # This ensures we always get the latest schema changes
        if is_sqlite:
            columns = self.inspector.get_columns(table_name)
            pk_columns = self.inspector.get_pk_constraint(table_name)
            foreign_keys = self.inspector.get_foreign_keys(table_name)
        else:
            columns = self.inspector.get_columns(table_name, schema=schema_name)
            pk_columns = self.inspector.get_pk_constraint(table_name, schema=schema_name)
            foreign_keys = self.inspector.get_foreign_keys(table_name, schema=schema_name)
        
        primary_key = pk_columns['constrained_columns'][0] if pk_columns['constrained_columns'] else None
        
        # Debug: print detected columns for troubleshooting
        column_names = [col['name'] for col in columns]
        schema_prefix = f"{schema_name}." if not is_sqlite else ""
        print(f"   📋 Detected columns for {schema_prefix}{table_name}: {', '.join(column_names)}")
        
        return {
            "table_name": table_name,
            "columns": columns,
            "primary_key": primary_key,
            "foreign_keys": foreign_keys
        }

class SchemaGenerator:
    def __init__(self, introspector: DatabaseIntrospector):
        self.introspector = introspector
    
    def _get_python_type(self, column_type: str) -> Type:
        """Map SQLAlchemy column types to Python types"""
        type_mapping = {
            'INTEGER': int,
            'BIGINT': int,
            'SERIAL': int,
            'TEXT': str,
            'VARCHAR': str,
            'CHAR': str,
            'BOOLEAN': bool,
            'TIMESTAMP': str,
            'TIMESTAMPTZ': str,
            'ARRAY': List[str],
            'JSON': Dict,
            'JSONB': Dict,
            'REAL': float,
            'DOUBLE': float,
        }
        
        # Extract base type from SQLAlchemy type string
        type_str = str(column_type)
        if '(' in type_str:
            base_type = type_str.split('(')[0].upper()
        else:
            base_type = type_str.upper()
        
        return type_mapping.get(base_type, str)
    
    def _is_optional(self, column_info: Dict) -> bool:
        """Check if a column is optional (nullable)"""
        return column_info.get('nullable', True)
    
    def generate_pydantic_schemas(self, table_name: str) -> Dict[str, Type[BaseModel]]:
        """Generate Pydantic schemas for a table"""
        table_info = self.introspector.get_table_info(table_name)
        
        # Base fields for output schema
        output_fields = {}
        input_fields = {}
        
        for column in table_info['columns']:
            column_name = column['name']
            python_type = self._get_python_type(column['type'])
            is_optional = self._is_optional(column)
            
            # Output schema includes all fields
            if is_optional:
                output_fields[column_name] = (Optional[python_type], None)
            else:
                output_fields[column_name] = (python_type, ...)
            
            # Input schema excludes auto-generated primary keys
            if column_name != table_info['primary_key']:
                if is_optional:
                    input_fields[column_name] = (Optional[python_type], None)
                else:
                    input_fields[column_name] = (python_type, ...)
        
        # Generate schemas
        schemas = {}
        
        # Output schema (for GET responses)
        # Allow extra fields to handle schema evolution - new columns added to DB will be included
        table_title = table_name.title()
        
        # Create models using DynamicBaseModel which allows extra fields
        # This ensures new columns added to the database will be included in API responses
        output_schema = create_model(
            f"{table_title}Out",
            __base__=DynamicBaseModel,
            **output_fields
        )
        schemas[f"{table_title}Out"] = output_schema
        
        # Input schema (for POST/PUT requests)
        input_schema = create_model(
            f"{table_title}In",
            __base__=DynamicBaseModel,
            **input_fields
        )
        schemas[f"{table_title}In"] = input_schema
        
        # Paginated schema
        paginated_schema = create_model(
            f"Paginated{table_title}s",
            items=(List[output_schema], ...),
            limit=(int, ...),
            offset=(int, ...),
            q=(Optional[str], None)
        )
        schemas[f"Paginated{table_title}s"] = paginated_schema
        
        return schemas

class AutoAPIGenerator:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.introspector = DatabaseIntrospector(db_session)
        self.schema_generator = SchemaGenerator(self.introspector)
        # Check if database is SQLite (doesn't support schemas)
        self.is_sqlite = 'sqlite' in str(db_session.bind.url).lower()
    
    def _get_table_ref(self, table_name: str, schema_name: str = "core") -> str:
        """Get table reference with or without schema prefix based on database type."""
        if self.is_sqlite:
            return table_name
        else:
            return f"{schema_name}.{table_name}"
    
    def generate_crud_router(self, table_name: str) -> APIRouter:
        """Generate a complete CRUD router for a table"""
        router = APIRouter(prefix=f"/auto/{table_name}", tags=[f"auto-{table_name}"])
        schemas = self.schema_generator.generate_pydantic_schemas(table_name)
        table_info = self.introspector.get_table_info(table_name)
        
        # Prepare foreign-key joins to expose human-readable labels
        fk_relationships = []
        fk_table_cache: Dict[str, Dict] = {}
        for idx, fk in enumerate(table_info.get('foreign_keys', [])):
            constrained_cols = fk.get('constrained_columns') or []
            referred_cols = fk.get('referred_columns') or []
            referred_table = fk.get('referred_table')
            if len(constrained_cols) != 1 or len(referred_cols) != 1 or not referred_table:
                continue
            
            local_col = constrained_cols[0]
            referred_col = referred_cols[0]
            referred_schema = fk.get('referred_schema') or "core"
            
            cache_key = f"{referred_schema}.{referred_table}"
            if cache_key not in fk_table_cache:
                try:
                    fk_table_cache[cache_key] = self.introspector.get_table_info(
                        referred_table,
                        schema_name=referred_schema
                    )
                except Exception:
                    continue
            
            ref_info = fk_table_cache[cache_key]
            # Determine a human-readable column to expose (prefer common names)
            preferred_names = ['name', 'title', 'full_name', 'label']
            display_column = None
            for candidate in preferred_names:
                if any(col['name'] == candidate for col in ref_info['columns']):
                    display_column = candidate
                    break
            if not display_column:
                for col in ref_info['columns']:
                    col_type = str(col['type']).upper()
                    if any(t in col_type for t in ['CHAR', 'TEXT', 'VARCHAR']) and col['name'] != referred_col:
                        display_column = col['name']
                        break
            if not display_column:
                continue
            
            alias = f"{referred_table}_fk_{idx}"
            if local_col.endswith('_id'):
                display_alias = f"{local_col[:-3]}_name"
            else:
                display_alias = f"{local_col}_name"
            
            # Get table references (schema-aware)
            table_ref = self._get_table_ref(table_name)
            referred_table_ref = self._get_table_ref(referred_table, referred_schema) if not self.is_sqlite else referred_table
            
            fk_relationships.append({
                "join_sql": (
                    f"LEFT JOIN {referred_table_ref} AS {alias} "
                    f"ON {table_ref}.{local_col} = {alias}.{referred_col}"
                ),
                "select_sql": f"{alias}.{display_column} AS {display_alias}",
                "alias": alias,
                "display_column": display_column
            })
        
        table_title = table_name.title()
        
        # GET /{table_name}/ - List all items
        # Note: Not using response_model to allow all fields from database to pass through
        @router.get("/")
        @limiter.limit("100/minute")  # Add this decorator
        def list_items(
            request: Request,
            q: Optional[str] = Query(None, description=f"Search in {table_name}"),
            sort: Optional[str] = Query(None, description="Sort field with - prefix for DESC"),
            limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0),
            db: Session = Depends(get_db),
            _auth: bool = _get_auth_dependency(require_auth=False)
        ):
            try:
                # Build WHERE clause
                where_conditions = ["1=1"]
                params = {"limit": limit, "offset": offset}
                
                if q:
                    # Create search conditions for text fields
                    search_fields = []
                    # SQLite uses LIKE (case-insensitive with COLLATE), PostgreSQL uses ILIKE
                    like_operator = "LIKE" if self.is_sqlite else "ILIKE"
                    for column in table_info['columns']:
                        col_type = str(column['type']).upper()
                        if any(t in col_type for t in ['TEXT', 'VARCHAR', 'CHAR']):
                            if self.is_sqlite:
                                search_fields.append(f"{column['name']} LIKE :q COLLATE NOCASE")
                            else:
                                search_fields.append(f"{column['name']} {like_operator} :q")
                    for rel in fk_relationships:
                        if self.is_sqlite:
                            search_fields.append(f"{rel['alias']}.{rel['display_column']} LIKE :q COLLATE NOCASE")
                        else:
                            search_fields.append(f"{rel['alias']}.{rel['display_column']} {like_operator} :q")
                    
                    if search_fields:
                        where_conditions.append(f"({' OR '.join(search_fields)})")
                        params["q"] = f"%{q}%"
                
                where_sql = " AND ".join(where_conditions)
                
                # Build ORDER BY clause
                sort_field = sort.lstrip("-") if sort else table_info['primary_key']
                order_dir = "DESC" if sort and sort.startswith("-") else "ASC"
                order_by_sql = f"{sort_field} {order_dir}"
                
                # Build SELECT clause - use SELECT * to always get all columns
                # This ensures new columns added to the database are included even if
                # they weren't in the schema when the router was generated
                # Note: With extra='allow' in Pydantic models, new columns will be accepted
                table_ref = self._get_table_ref(table_name)
                select_parts = [f"{table_ref}.*"] + [rel["select_sql"] for rel in fk_relationships]
                select_sql = ", ".join(select_parts)
                join_sql = " ".join(rel["join_sql"] for rel in fk_relationships)
                
                # Execute query
                sql = f"""
                    SELECT {select_sql}
                    FROM {table_ref}
                    {join_sql}
                    WHERE {where_sql}
                    ORDER BY {order_by_sql}
                    LIMIT :limit OFFSET :offset
                """
                
                rows = db.execute(text(sql), params).mappings().all()
                
                # Debug: Log what columns are actually in the database result
                if rows:
                    first_row_keys = list(dict(rows[0]).keys())
                    print(f"   🔍 DEBUG: Raw database columns for {table_name}: {first_row_keys}")
                
                # Convert rows to response items - merge Pydantic model with raw DB data
                # This ensures ALL fields from database are included, even if not in schema
                items = []
                for row in rows:
                    row_dict = dict(row)
                    
                    # Get schema fields for comparison
                    try:
                        schema_fields = set(schemas[f"{table_title}Out"].model_fields.keys() if hasattr(schemas[f"{table_title}Out"], 'model_fields') else schemas[f"{table_title}Out"].__fields__.keys())
                    except:
                        schema_fields = set()
                    
                    # Create Pydantic model for validation (if it works)
                    try:
                        item = schemas[f"{table_title}Out"](**row_dict)
                        # Serialize the model
                        if hasattr(item, 'model_dump'):
                            item_dict = item.model_dump(exclude_unset=False, exclude_none=False)
                        else:
                            item_dict = item.dict(exclude_unset=False, exclude_none=False)
                        
                        # CRITICAL: Merge raw database dict with Pydantic output
                        # This ensures fields not in the schema are still included
                        # Pydantic extra='allow' only prevents validation errors, doesn't serialize extra fields
                        merged_dict = {**item_dict, **row_dict}
                        items.append(merged_dict)
                    except Exception as e:
                        # If Pydantic fails, just return raw database data
                        print(f"   ⚠️  Pydantic validation failed for {table_name}: {e}")
                        items.append(row_dict)
                
                return {
                    "items": items,
                    "limit": limit,
                    "offset": offset,
                    "q": q
                }
                
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
        # GET /{table_name}/{id} - Get single item
        # Note: Not using response_model to allow all fields from database to pass through
        @router.get("/{item_id}")
        def get_item(
            item_id: int,
            db: Session = Depends(get_db),
            _auth: bool = _get_auth_dependency(require_auth=False)
        ):
            try:
                table_ref = self._get_table_ref(table_name)
                select_parts = [f"{table_ref}.*"] + [rel["select_sql"] for rel in fk_relationships]
                select_sql = ", ".join(select_parts)
                join_sql = " ".join(rel["join_sql"] for rel in fk_relationships)
                sql = f"""
                    SELECT {select_sql}
                    FROM {table_ref}
                    {join_sql}
                    WHERE {table_info['primary_key']} = :id
                """
                row = db.execute(text(sql), {"id": item_id}).mappings().first()
                
                if not row:
                    raise HTTPException(status_code=404, detail=f"{table_name} not found")
                
                row_dict = dict(row)
                
                # Create Pydantic model and merge with raw DB data to include all fields
                try:
                    item = schemas[f"{table_title}Out"](**row_dict)
                    if hasattr(item, 'model_dump'):
                        item_dict = item.model_dump(exclude_unset=False, exclude_none=False)
                    else:
                        item_dict = item.dict(exclude_unset=False, exclude_none=False)
                    # Merge to ensure all DB fields are included
                    return {**item_dict, **row_dict}
                except Exception as e:
                    # Fallback to raw data if Pydantic fails
                    print(f"   ⚠️  Pydantic validation failed: {e}")
                    return row_dict
                
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
        # POST /{table_name}/ - Create new item
        # Note: Not using response_model to allow all fields from database to pass through
        @router.post("/")
        @limiter.limit("20/minute")
        def create_item(
            request: Request,
            item: schemas[f"{table_title}In"],
            db: Session = Depends(get_db),
            _auth: bool = _get_auth_dependency(require_auth=True)
        ):
            try:
                # Convert Pydantic model to dict, excluding None values
                item_data = item.dict(exclude_none=True)
                
                # Build INSERT query
                table_ref = self._get_table_ref(table_name)
                columns = list(item_data.keys())
                values = [f":{col}" for col in columns]
                
                # SQLite doesn't support RETURNING, PostgreSQL does
                if self.is_sqlite:
                    sql = f"""
                        INSERT INTO {table_ref} ({', '.join(columns)})
                        VALUES ({', '.join(values)})
                    """
                else:
                    sql = f"""
                        INSERT INTO {table_ref} ({', '.join(columns)})
                        VALUES ({', '.join(values)})
                        RETURNING *
                    """
                
                if self.is_sqlite:
                    # SQLite doesn't support RETURNING, so we need to get the last rowid
                    db.execute(text(sql), item_data)
                    db.commit()
                    # Get the inserted row
                    last_id = db.execute(text(f"SELECT last_insert_rowid()")).scalar()
                    result = db.execute(text(f"SELECT * FROM {table_ref} WHERE {table_info['primary_key']} = :id"), {"id": last_id}).mappings().first()
                    result_dict = dict(result) if result else item_data
                else:
                    result = db.execute(text(sql), item_data).mappings().first()
                    db.commit()
                    result_dict = dict(result)
                
                # Create Pydantic model and merge with raw DB data to include all fields
                try:
                    item = schemas[f"{table_title}Out"](**result_dict)
                    if hasattr(item, 'model_dump'):
                        item_dict = item.model_dump(exclude_unset=False, exclude_none=False)
                    else:
                        item_dict = item.dict(exclude_unset=False, exclude_none=False)
                    # Merge to ensure all DB fields are included
                    return {**item_dict, **result_dict}
                except Exception as e:
                    print(f"   ⚠️  Pydantic validation failed: {e}")
                    return result_dict
                
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Error creating {table_name}: {str(e)}")
        
        # PUT /{table_name}/{id} - Update item
        # Note: Not using response_model to allow all fields from database to pass through
        @router.put("/{item_id}")
        def update_item(
            item_id: int,
            item: schemas[f"{table_title}In"],
            db: Session = Depends(get_db),
            _auth: bool = _get_auth_dependency(require_auth=True)
        ):
            try:
                item_data = item.dict(exclude_none=True)
                table_ref = self._get_table_ref(table_name)
                
                # Build UPDATE query
                set_clauses = [f"{col} = :{col}" for col in item_data.keys()]
                
                # SQLite doesn't support RETURNING, PostgreSQL does
                if self.is_sqlite:
                    sql = f"""
                        UPDATE {table_ref}
                        SET {', '.join(set_clauses)}
                        WHERE {table_info['primary_key']} = :id
                    """
                else:
                    sql = f"""
                        UPDATE {table_ref}
                        SET {', '.join(set_clauses)}
                        WHERE {table_info['primary_key']} = :id
                        RETURNING *
                    """
                
                item_data['id'] = item_id
                
                if self.is_sqlite:
                    # SQLite doesn't support RETURNING, so execute update then fetch
                    result = db.execute(text(sql), item_data)
                    db.commit()
                    if result.rowcount == 0:
                        raise HTTPException(status_code=404, detail=f"{table_name} not found")
                    # Fetch the updated row
                    result = db.execute(text(f"SELECT * FROM {table_ref} WHERE {table_info['primary_key']} = :id"), {"id": item_id}).mappings().first()
                    result_dict = dict(result) if result else item_data
                else:
                    result = db.execute(text(sql), item_data).mappings().first()
                    if not result:
                        raise HTTPException(status_code=404, detail=f"{table_name} not found")
                    db.commit()
                    result_dict = dict(result)
                
                # Create Pydantic model and merge with raw DB data to include all fields
                try:
                    item = schemas[f"{table_title}Out"](**result_dict)
                    if hasattr(item, 'model_dump'):
                        item_dict = item.model_dump(exclude_unset=False, exclude_none=False)
                    else:
                        item_dict = item.dict(exclude_unset=False, exclude_none=False)
                    # Merge to ensure all DB fields are included
                    return {**item_dict, **result_dict}
                except Exception as e:
                    print(f"   ⚠️  Pydantic validation failed: {e}")
                    return result_dict
                
            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Error updating {table_name}: {str(e)}")
        
        # DELETE /{table_name}/{id} - Delete item
        @router.delete("/{item_id}")
        def delete_item(
            item_id: int,
            db: Session = Depends(get_db),
            _auth: bool = _get_auth_dependency(require_auth=True)
        ):
            try:
                table_ref = self._get_table_ref(table_name)
                sql = f"DELETE FROM {table_ref} WHERE {table_info['primary_key']} = :id"
                result = db.execute(text(sql), {"id": item_id})
                
                if result.rowcount == 0:
                    raise HTTPException(status_code=404, detail=f"{table_name} not found")
                
                db.commit()
                return {"message": f"{table_name} deleted successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Error deleting {table_name}: {str(e)}")
        
        return router

def auto_generate_all_routers(db_session: Session) -> List[APIRouter]:
    """Generate routers for all tables in the core schema"""
    generator = AutoAPIGenerator(db_session)
    tables = generator.introspector.get_tables_in_schema("core")
    
    # Filter out junction tables and system tables
    excluded_tables = _get_excluded_tables()
    main_tables = [table for table in tables if table not in excluded_tables]
    
    routers = []
    for table in main_tables:
        try:
            router = generator.generate_crud_router(table)
            routers.append(router)
        except Exception as e:
            print(f"Warning: Could not generate router for {table}: {e}")
    
    return routers


def _get_excluded_tables() -> Set[str]:
    """Read excluded tables from AUTO_API_EXCLUDE environment variable"""
    exclude_env = os.getenv("AUTO_API_EXCLUDE", "")
    return {name.strip() for name in exclude_env.split(",") if name.strip()}


def get_available_auto_tables(db_session: Session) -> List[str]:
    """Return list of auto-generated tables after applying exclusions."""
    generator = AutoAPIGenerator(db_session)
    tables = generator.introspector.get_tables_in_schema("core")
    excluded_tables = _get_excluded_tables()
    return [table for table in tables if table not in excluded_tables]