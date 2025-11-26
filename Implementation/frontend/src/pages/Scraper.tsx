import { useState } from 'react'
import api from '@/lib/axios'
import { Loader2, Search, CheckCircle2, ExternalLink } from 'lucide-react'

interface SearchResult {
  query: string
  rank: number
  title: string
  url: string
  snippet: string
  source: string
  scraped_at: string
}

interface ScrapedEntity {
  url: string
  label: string
  title: string
  source_query: string
  scraped_status: string
  scraped_at: string
  llm_payload: any
}

export default function Scraper() {
  const [topic, setTopic] = useState('')
  const [dataSpecification, setDataSpecification] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set())
  const [scrapedData, setScrapedData] = useState<ScrapedEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'input' | 'results' | 'scraped'>('input')

  // Flexible function to detect what fields user wants from their free-form input
  const detectRequestedFields = (dataSpec: string): string[] => {
    if (!dataSpec) return []
    
    const specLower = dataSpec.toLowerCase()
    const requestedFields: string[] = []
    
    // Field mapping with flexible keyword matching
    const fieldMappings: { [key: string]: string[] } = {
      'contact_email': ['email', 'contact email', 'e-mail', 'mail', 'contact', 'correspondence'],
      'phone': ['phone', 'telephone', 'tel', 'call', 'number'],
      'address': ['address', 'location', 'street', 'postal'],
      'city': ['city', 'town'],
      'country': ['country', 'nation'],
      'website': ['website', 'site', 'url', 'web', 'homepage'],
      'genres': ['genre', 'category', 'type', 'kind'],
      'reading_period': ['reading period', 'submission period', 'open', 'deadline', 'window'],
      'reading_fee': ['fee', 'cost', 'price', 'charge', 'payment'],
      'submission_methods': ['submission', 'submit', 'guideline', 'how to submit', 'method'],
      'response_time': ['response', 'reply', 'answer time', 'turnaround'],
      'name': ['name', 'title', 'company', 'organization']
    }
    
    // Check each field mapping
    Object.keys(fieldMappings).forEach(field => {
      const keywords = fieldMappings[field]
      if (keywords.some(keyword => specLower.includes(keyword))) {
        requestedFields.push(field)
      }
    })
    
    return requestedFields
  }

  // Check if requested fields are missing
  const getMissingFields = (dataSpec: string, payload: any): string[] => {
    if (!dataSpec || !payload) return []
    
    const requestedFields = detectRequestedFields(dataSpec)
    const missing: string[] = []
    
    requestedFields.forEach(field => {
      const value = payload[field]
      const isEmpty = value === null || value === undefined || 
                     (Array.isArray(value) && value.length === 0) ||
                     (typeof value === 'string' && value.trim() === '')
      
      if (isEmpty) {
        // Convert field name to readable label
        const label = field.split('_').map(w => 
          w.charAt(0).toUpperCase() + w.slice(1)
        ).join(' ')
        missing.push(label)
      }
    })
    
    return missing
  }

  const handleSearch = async () => {
    if (!topic.trim()) {
      setError('Please enter a topic')
      return
    }

    setLoading(true)
    setError(null)
    setSearchResults([])
    setSelectedUrls(new Set())
    setScrapedData([])

    try {
      const response = await api.post('/scraper/generate-search', {
        topic: topic.trim(),
        data_specification: dataSpecification.trim() || null
      })

      setSearchResults(response.data.search_results)
      setStep('results')
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail 
        || err.response?.data?.message 
        || err.message 
        || `Failed to perform search: ${err.response?.statusText || err.response?.status || 'Unknown error'}`
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const toggleUrlSelection = (url: string) => {
    const newSelected = new Set(selectedUrls)
    if (newSelected.has(url)) {
      newSelected.delete(url)
    } else {
      newSelected.add(url)
    }
    setSelectedUrls(newSelected)
  }

  const handleScrape = async () => {
    if (selectedUrls.size === 0) {
      setError('Please select at least one URL')
      return
    }

    setLoading(true)
    setError(null)
    setScrapedData([])

    try {
      const response = await api.post('/scraper/scrape-urls', {
        urls: Array.from(selectedUrls),
        data_specification: dataSpecification.trim() || null
      })

      setScrapedData(response.data.results)
      setStep('scraped')
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail 
        || err.response?.data?.message 
        || err.message 
        || `Failed to scrape URLs: ${err.response?.statusText || err.response?.status || 'Unknown error'}`
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">
          <span className="bg-gradient-to-r from-[#5E60F8] to-[#D946EF] bg-clip-text text-transparent">
            Web Scraper
          </span>
        </h1>
        <p className="mt-2 text-sm sm:text-base text-[#64748B]">
          Search for data from any industry and extract structured information
        </p>
      </div>

      {/* Step 1: Input Form */}
      {step === 'input' && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 sm:p-8 space-y-6">
          <div>
            <label htmlFor="topic" className="block text-sm font-medium text-[#0F172A] mb-2">
              Topic / Search Prompt *
            </label>
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !loading && topic.trim()) {
                  handleSearch()
                }
              }}
              placeholder="e.g., poetry presses in Canada"
              className="w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#5E60F8] focus:border-[#5E60F8] transition-colors"
              disabled={loading}
            />
            <p className="mt-1 text-sm text-[#64748B]">
              Enter a natural language description of what you want to search for
            </p>
          </div>

          <div>
            <label htmlFor="dataSpec" className="block text-sm font-medium text-[#0F172A] mb-2">
              Data Specification (Optional)
            </label>
            <textarea
              id="dataSpec"
              value={dataSpecification}
              onChange={(e) => setDataSpecification(e.target.value)}
              placeholder="e.g., Focus on extracting press name, contact email, and submission guidelines"
              rows={4}
              className="w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#5E60F8] focus:border-[#5E60F8] transition-colors resize-none"
              disabled={loading}
            />
            <p className="mt-1 text-sm text-[#64748B]">
              Specify what data you want extracted.
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <button
            onClick={handleSearch}
            disabled={loading || !topic.trim()}
            className="w-full bg-gradient-to-r from-[#5E60F8] to-[#D946EF] text-white px-6 py-3 rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 font-medium"
          >
            {loading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Searching...
              </>
            ) : (
              <>
                <Search className="h-5 w-5" />
                Search
              </>
            )}
          </button>
        </div>
      )}

      {/* Step 2: Search Results */}
      {step === 'results' && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 sm:p-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-semibold text-[#0F172A]">
                  Search Results
                </h2>
                <p className="text-sm text-[#64748B] mt-1">
                  {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found
                </p>
              </div>
              <button
                onClick={() => {
                  setStep('input')
                  setSearchResults([])
                  setSelectedUrls(new Set())
                }}
                className="text-sm text-[#5E60F8] hover:text-[#D946EF] font-medium transition-colors"
              >
                New Search
              </button>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
                {error}
              </div>
            )}

            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
              {searchResults.map((result, idx) => (
                <div
                  key={idx}
                  className={`border rounded-lg p-4 cursor-pointer transition-all ${
                    selectedUrls.has(result.url)
                      ? 'border-[#5E60F8] bg-[#EEF2FF] shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 hover:shadow-sm'
                  }`}
                  onClick={() => toggleUrlSelection(result.url)}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-1">
                      {selectedUrls.has(result.url) ? (
                        <CheckCircle2 className="h-5 w-5 text-[#5E60F8]" />
                      ) : (
                        <div className="h-5 w-5 rounded-full border-2 border-slate-300" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-[#0F172A] mb-1">{result.title}</h3>
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-sm text-[#5E60F8] hover:text-[#D946EF] hover:underline flex items-center gap-1 mb-2 break-all"
                      >
                        {result.url}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                      {result.snippet && (
                        <p className="mt-1 text-sm text-[#64748B] line-clamp-2">{result.snippet}</p>
                      )}
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#64748B]">
                        <span className="bg-slate-100 px-2 py-1 rounded">Query: {result.query}</span>
                        <span className="bg-slate-100 px-2 py-1 rounded">Rank: {result.rank}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 flex items-center justify-between pt-4 border-t border-slate-200">
              <p className="text-sm text-[#64748B]">
                {selectedUrls.size} URL{selectedUrls.size !== 1 ? 's' : ''} selected
              </p>
              <button
                onClick={handleScrape}
                disabled={loading || selectedUrls.size === 0}
                className="bg-gradient-to-r from-green-600 to-emerald-600 text-white px-6 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 font-medium"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Scraping...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4" />
                    Scrape Selected URLs
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Scraped Data */}
      {step === 'scraped' && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 sm:p-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-semibold text-[#0F172A]">
                  Scraped Data
                </h2>
                <p className="text-sm text-[#64748B] mt-1">
                  {scrapedData.length} entit{scrapedData.length !== 1 ? 'ies' : 'y'} extracted
                </p>
              </div>
              <button
                onClick={() => {
                  setStep('input')
                  setSearchResults([])
                  setSelectedUrls(new Set())
                  setScrapedData([])
                }}
                className="text-sm text-[#5E60F8] hover:text-[#D946EF] font-medium transition-colors"
              >
                New Search
              </button>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
                {error}
              </div>
            )}

            {/* Summary of missing data */}
            {dataSpecification && (() => {
              const entitiesWithMissing = scrapedData.filter(item => {
                if (!item.llm_payload) return false
                return getMissingFields(dataSpecification, item.llm_payload).length > 0
              })
              
              if (entitiesWithMissing.length > 0) {
                return (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
                    <div className="flex items-start gap-2">
                      <span className="text-amber-600">⚠️</span>
                      <div>
                        <p className="text-sm font-medium text-amber-900">
                          {entitiesWithMissing.length} of {scrapedData.length} entities are missing requested data
                        </p>
                        <p className="text-xs text-amber-700 mt-1">
                          Requested: "{dataSpecification}"
                        </p>
                      </div>
                    </div>
                  </div>
                )
              }
              return null
            })()}

            <div className="space-y-4">
              {scrapedData.map((item, idx) => (
                <div key={idx} className="border border-slate-200 rounded-lg p-5 hover:shadow-sm transition-shadow">
                  <div className="mb-3 flex items-center gap-2 flex-wrap">
                    <span className={`inline-block text-xs px-2 py-1 rounded font-medium ${
                      item.scraped_status === 'ok' 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {item.scraped_status}
                    </span>
                    {item.scraped_at && (
                      <span className="text-xs text-[#64748B]">
                        {new Date(item.scraped_at).toLocaleString()}
                      </span>
                    )}
                    {/* Show missing fields badge */}
                    {dataSpecification && item.llm_payload && (() => {
                      const missing = getMissingFields(dataSpecification, item.llm_payload)
                      return missing.length > 0 ? (
                        <span className="inline-block text-xs px-2 py-1 rounded font-medium bg-amber-100 text-amber-700">
                          Missing: {missing.join(', ')}
                        </span>
                      ) : null
                    })()}
                  </div>
                  
                  {item.llm_payload ? (
                    <div className="space-y-3">
                      <h3 className="font-semibold text-lg text-[#0F172A]">
                        {item.llm_payload.name || 'Unnamed Entity'}
                      </h3>
                      
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                        {item.llm_payload.website && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Website:</span>{' '}
                            <a 
                              href={item.llm_payload.website} 
                              target="_blank" 
                              rel="noopener noreferrer" 
                              className="text-[#5E60F8] hover:text-[#D946EF] hover:underline"
                            >
                              {item.llm_payload.website}
                            </a>
                          </div>
                        )}
                        {/* Contact Email - show if requested or if exists */}
                        {((dataSpecification && detectRequestedFields(dataSpecification).includes('contact_email')) || 
                          item.llm_payload.contact_email) && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Email:</span>{' '}
                            {item.llm_payload.contact_email ? (
                              <a 
                                href={`mailto:${item.llm_payload.contact_email}`}
                                className="text-[#5E60F8] hover:text-[#D946EF] hover:underline"
                              >
                                {item.llm_payload.contact_email}
                              </a>
                            ) : (
                              <span className="text-amber-600 italic text-xs">Not found on page</span>
                            )}
                          </div>
                        )}
                        {item.llm_payload.city && (
                          <div>
                            <span className="font-medium text-[#0F172A]">City:</span>{' '}
                            <span className="text-[#64748B]">{item.llm_payload.city}</span>
                          </div>
                        )}
                        {item.llm_payload.country && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Country:</span>{' '}
                            <span className="text-[#64748B]">{item.llm_payload.country}</span>
                          </div>
                        )}
                        {item.llm_payload.genres && item.llm_payload.genres.length > 0 && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Genres:</span>{' '}
                            <span className="text-[#64748B]">
                              {item.llm_payload.genres.map((g: string, i: number) => (
                                <span key={i}>
                                  {g}
                                  {i < item.llm_payload.genres.length - 1 ? ', ' : ''}
                                </span>
                              ))}
                            </span>
                          </div>
                        )}
                        {item.llm_payload.reading_period && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Reading Period:</span>{' '}
                            <span className="text-[#64748B]">{item.llm_payload.reading_period}</span>
                          </div>
                        )}
                        {item.llm_payload.reading_fee !== undefined && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Reading Fee:</span>{' '}
                            <span className="text-[#64748B]">${item.llm_payload.reading_fee}</span>
                          </div>
                        )}
                        {item.llm_payload.submission_methods && item.llm_payload.submission_methods.length > 0 && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Submission Methods:</span>{' '}
                            <span className="text-[#64748B]">
                              {item.llm_payload.submission_methods.map((m: string, i: number) => (
                                <span key={i}>
                                  {m}
                                  {i < item.llm_payload.submission_methods.length - 1 ? ', ' : ''}
                                </span>
                              ))}
                            </span>
                          </div>
                        )}
                        {item.llm_payload.response_time && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Response Time:</span>{' '}
                            <span className="text-[#64748B]">{item.llm_payload.response_time}</span>
                          </div>
                        )}
                      </div>
                      
                      {item.llm_payload.notes && (
                        <div className="mt-3 pt-3 border-t border-slate-200">
                          <span className="font-medium text-[#0F172A]">Notes:</span>{' '}
                          <span className="text-sm text-[#64748B]">{item.llm_payload.notes}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-[#64748B]">No data extracted</p>
                  )}
                  
                  <div className="mt-4 pt-3 border-t border-slate-200">
                    <a 
                      href={item.url} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="text-xs text-[#5E60F8] hover:text-[#D946EF] hover:underline flex items-center gap-1"
                    >
                      Source: {item.url}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

