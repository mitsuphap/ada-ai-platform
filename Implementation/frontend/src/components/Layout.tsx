import { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A]">
      <nav className="bg-gradient-to-r from-[#5E60F8] to-[#D946EF] shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="py-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <Link
                to="/"
                className="text-lg sm:text-xl font-semibold text-white hover:text-white/90 transition-colors"
              >
                Ada Automated Data Intelligence
              </Link>
              <p className="text-sm text-white/75">
                Unified visibility for exploration.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex gap-4">
                <Link
                  to="/"
                  className="text-xs sm:text-sm text-white/90 hover:text-white font-medium transition-colors"
                >
                  Dashboard
                </Link>
                <Link
                  to="/scraper"
                  className="text-xs sm:text-sm text-white/90 hover:text-white font-medium transition-colors"
                >
                  Scraper
                </Link>
              </div>
              <div className="text-xs sm:text-sm text-white/80 font-medium md:text-right">
                Real-time schema awareness • Secure API oversight
              </div>
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {children}
      </main>
    </div>
  )
}

