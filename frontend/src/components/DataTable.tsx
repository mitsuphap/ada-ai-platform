import { useState, useEffect, useRef } from 'react'
import { useAutoTable } from '@/hooks/useAutoTable'
import { formatValue } from '@/lib/utils'
import { ChevronLeft, ChevronRight, Search, Loader2 } from 'lucide-react'

interface DataTableProps {
  tableName: string
}

export default function DataTable({ tableName }: DataTableProps) {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(0)
  const limit = 20
  const inputRef = useRef<HTMLInputElement>(null)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(0) // Reset to first page when search changes
    }, 300) // 300ms delay

    return () => clearTimeout(timer)
  }, [search])

  // Keep focus on input after re-renders
  useEffect(() => {
    if (inputRef.current && document.activeElement !== inputRef.current) {
      // Only restore focus if the input was previously focused
      const wasFocused = inputRef.current === document.activeElement || 
                         inputRef.current.contains(document.activeElement)
      if (!wasFocused && search.length > 0) {
        // Only auto-focus if user was typing (search has content)
        // This prevents auto-focusing when just navigating
        return
      }
    }
  })

  const { data, isLoading, error } = useAutoTable(tableName, {
    q: debouncedSearch || undefined,
    limit,
    offset: page * limit,
  })

  // Restructure to keep search input visible during loading
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Search - Always visible */}
      <div className="border-b border-slate-200 bg-[#F8FAFC] p-6">
        <div className="mb-4">
          <label
            htmlFor="search-input"
            className="flex items-center gap-2 text-sm font-medium text-[#0F172A]"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#EEF2FF] to-[#F4EDFF] text-[#5E60F8]">
              <Search className="h-4 w-4" aria-hidden="true" />
            </div>
            Search records
          </label>
          <p className="ml-10 mt-2 text-xs text-[#64748B]">
            Use keywords to query across every column. Results update automatically once you pause typing.
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            id="search-input"
            ref={inputRef}
            type="text"
            placeholder="Search across all columns..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
            }}
            className="w-full rounded-xl border border-slate-300 bg-white py-3.5 pl-12 pr-4 text-sm text-[#0F172A] shadow-sm transition-colors placeholder:text-slate-400 focus:border-[#5E60F8] focus:outline-none focus:ring focus:ring-[#5E60F8]/20"
            autoFocus={false}
          />
          {isLoading && debouncedSearch && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <Loader2 className="h-5 w-5 animate-spin text-[#5E60F8]" />
            </div>
          )}
        </div>
      </div>

      {/* Loading state - but keep search visible */}
      {isLoading && !data && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-[#5E60F8]" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="m-6 rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800 shadow-sm">
          <p className="font-medium">Error loading data: {(error as Error).message}</p>
        </div>
      )}

      {/* Table content */}
      {!isLoading && data && data.items.length === 0 && (
        <div className="m-6 rounded-xl border border-amber-200/60 bg-amber-50/60 p-8 text-center shadow-sm">
          {debouncedSearch ? (
            <>
              <p className="text-lg font-semibold text-amber-900">No records matched your search</p>
              <p className="mt-2 text-sm text-amber-800">
                Adjust your filters or clear the search field to view every available record.
              </p>
            </>
          ) : (
            <>
              <p className="text-lg font-semibold text-amber-900">This table is currently empty</p>
              <p className="mt-2 text-sm text-amber-800">
                Add records through the API or upstream pipeline to begin monitoring this dataset.
              </p>
            </>
          )}
        </div>
      )}

      {!isLoading && data && data.items.length > 0 && (
        <>
          {/* Table */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-gradient-to-r from-[#5E60F8] via-[#7A5FF7] to-[#D946EF]">
                <tr>
                  {Object.keys(data.items[0] || {}).map((col) => (
                    <th
                      key={col}
                      className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-white"
                    >
                      {col.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {data.items.map((item: any, idx: number) => (
                  <tr 
                    key={item.id || idx} 
                    className={`transition-colors duration-200 hover:bg-[#EEF2FF] ${
                      idx % 2 === 0 ? 'bg-white' : 'bg-[#F8FAFC]'
                    }`}
                  >
                    {Object.keys(data.items[0] || {}).map((col) => (
                      <td key={col} className="whitespace-nowrap px-6 py-4 text-sm font-medium text-[#0F172A]">
                        {formatValue(item[col])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex flex-col items-start justify-between gap-4 border-t border-slate-200 bg-[#F8FAFC] px-6 py-5 sm:flex-row sm:items-center">
            <div className="space-y-1 text-sm text-[#64748B]">
              <div className="font-medium text-[#0F172A]">
                Showing {data.offset + 1} to {Math.min(data.offset + data.items.length, data.offset + limit)} of{' '}
                {data.items.length === limit ? `${data.offset + data.items.length}+` : data.offset + data.items.length} records
              </div>
              <div className="text-xs">
                {data.items.length === limit ? 'More results available — use the arrows to keep browsing.' : 'All available records are visible on this page.'}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden text-xs font-medium text-[#64748B] sm:inline">Navigate</span>
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#5E60F8] to-[#7A5FF7] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-400 disabled:text-white/70"
                title="Previous page"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Previous</span>
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={data.items.length < limit}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#7A5FF7] to-[#D946EF] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-400 disabled:text-white/70"
                title="Next page"
              >
                <span className="hidden sm:inline">Next</span>
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

