export interface PaginatedResponse<T> {
  items: T[]
  limit: number
  offset: number
  q?: string | null
}

export interface AutoTableInfo {
  name: string
  endpoint: string
  count?: number
}

