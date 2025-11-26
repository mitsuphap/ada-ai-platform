import { useQuery } from '@tanstack/react-query'
import api from '@/lib/axios'
import { Link } from 'react-router-dom'
import { Database, Loader2 } from 'lucide-react'

interface TableSummary {
  name: string
  count: number | null
}

export default function Dashboard() {
  const { data: tables, isLoading } = useQuery({
    queryKey: ['availableTables'],
    queryFn: async () => {
      // Try to get health endpoint first
      try {
        await api.get('/health')
      } catch (e) {
        throw new Error('Cannot connect to API')
      }
      
      // Fetch the list of available auto-generated tables from the API
      let tableNames: string[] = []
      try {
        const { data } = await api.get<{ tables?: string[] }>('/auto/tables')
        if (Array.isArray(data?.tables)) {
          tableNames = data.tables
        }
      } catch (err) {
        console.error('Failed to fetch auto tables', err)
      }

      const availableTables: TableSummary[] = []

      // Check which tables exist by trying to fetch one item
      for (const table of tableNames) {
        try {
          const response = await api.get(`/auto/${table}`, { params: { limit: 1 } })
          const headerTotal = response.headers['x-total-count']
          let count: number | null = null
          
          if (headerTotal) {
            const parsed = parseInt(headerTotal, 10)
            count = Number.isNaN(parsed) ? null : parsed
          } else if (typeof response.data?.total === 'number') {
            count = response.data.total
          } else if (Array.isArray(response.data?.items)) {
            count = response.data.items.length
          }
          
          availableTables.push({ name: table, count })
        } catch (e) {
          // Table doesn't exist or endpoint not available
        }
      }
      
      return availableTables
    },
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-[#5E60F8]" />
      </div>
    )
  }

  return (
    <div>
      {/* Header Section */}
      <div className="mb-12 space-y-3">
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">
          <span className="bg-gradient-to-r from-[#5E60F8] to-[#D946EF] bg-clip-text text-transparent">
            Publishing Data Intelligence
          </span>
        </h1>
        <p className="text-sm sm:text-base text-[#64748B] max-w-2xl">
          Monitor live publishing datasets, validate table freshness, and explore generated REST resources from a single dashboard.
        </p>
      </div>

      {/* Tables Section */}
      <div className="mb-6 flex flex-col gap-2">
        <h2 className="text-lg sm:text-xl font-semibold text-[#0F172A]">
          Available Tables
        </h2>
        <p className="text-sm text-[#64748B]">
          Select a resource to inspect data structure, run instant searches, and audit records on demand.
        </p>
      </div>
      
      {tables && tables.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {tables.map(({ name }, index: number) => (
            <Link
              key={name}
              to={`/table/${name}`}
              className="group relative overflow-hidden rounded-2xl bg-white border border-slate-200 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-[#5E60F8]/40"
            >
              <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#5E60F8] via-[#7A5FF7] to-[#D946EF]" />
              <div className="p-6 flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#EEF2FF] to-[#F5F3FF] text-[#5E60F8] ring-1 ring-[#5E60F8]/15">
                  <Database className="h-6 w-6" aria-hidden="true" />
                </div>
                <div className="flex-1 space-y-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-[#64748B]">
                      Data Source {index + 1}
                    </p>
                    <h3 className="text-lg font-semibold text-[#0F172A] capitalize">
                      {name.replace(/_/g, ' ')}
                    </h3>
                  </div>
                  <span className="text-sm text-[#64748B] block">
                    View schema & run quick queries
                  </span>
                </div>
              </div>
              <div className="px-6 pb-6 text-sm font-medium text-[#5E60F8] group-hover:text-[#D946EF] transition-colors">
                Explore dataset
                <span aria-hidden="true" className="ml-2 inline-block transition-transform group-hover:translate-x-1">
                  →
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-amber-200/60 bg-amber-50/60 p-6 shadow-sm">
          <p className="mb-2 text-sm font-semibold text-amber-900">No tables detected</p>
          <p className="text-sm text-amber-800">
            Verify that the backend is running and the database connection is healthy. Once tables are reachable they
            will surface here automatically.
          </p>
        </div>
      )}
    </div>
  )
}

