import { useParams, Link } from 'react-router-dom'
import DataTable from '@/components/DataTable'
import { ArrowLeft, Database } from 'lucide-react'

export default function TableDetail() {
  const { tableName } = useParams<{ tableName: string }>()

  if (!tableName) {
    return <div>Table not found</div>
  }

  return (
    <div className="space-y-8">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-sm font-medium text-[#5E60F8] transition-colors hover:text-[#D946EF]"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to dashboard
      </Link>

      {/* Table Header */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#EEF2FF] to-[#F4EDFF] text-[#5E60F8] ring-1 ring-[#5E60F8]/15">
            <Database className="h-6 w-6" aria-hidden="true" />
          </div>
          <div className="flex-1 space-y-2">
            <h1 className="text-2xl sm:text-3xl font-semibold capitalize text-[#0F172A]">
              {tableName.replace(/_/g, ' ')}
            </h1>
            <p className="text-sm text-[#64748B]">
              Review the latest records, search across fields, and audit schema changes for this generated resource.
            </p>
          </div>
        </div>
      </div>

      <DataTable tableName={tableName} />
    </div>
  )
}

