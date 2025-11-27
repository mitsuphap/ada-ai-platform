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
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set())
  const [scrapedData, setScrapedData] = useState<ScrapedEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'input' | 'results' | 'scraped'>('input')
  const [totalAvailableLinks, setTotalAvailableLinks] = useState<number | null>(null)
  const [hasMoreLinks, setHasMoreLinks] = useState(false)
  const [scrapingMore, setScrapingMore] = useState(false)

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
    setTotalAvailableLinks(null)
    setHasMoreLinks(false)

    try {
      // Use the automatic endpoint that does: search -> classify -> filter (confidence >= 0.95) -> scrape top 10
      const response = await api.post('/scraper/search-and-scrape-auto', {
        topic: topic.trim(),
        data_specification: topic.trim() || null
      })

      setScrapedData(response.data.results)
      setTotalAvailableLinks(response.data.total_available_links || null)
      setHasMoreLinks(response.data.has_more || false)
      setStep('scraped') // Skip the results selection step, go directly to scraped data
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail 
        || err.response?.data?.message 
        || err.message 
        || `Failed to search and scrape: ${err.response?.statusText || err.response?.status || 'Unknown error'}`
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const handleScrapeMore = async () => {
    if (!topic.trim()) {
      setError('Topic is required')
      return
    }

    setScrapingMore(true)
    setError(null)

    try {
      const response = await api.post('/scraper/scrape-more', {
        topic: topic.trim(),
        data_specification: topic.trim() || null
      })

      // Append new results to existing scraped data
      setScrapedData(prev => [...prev, ...response.data.results])
      setHasMoreLinks(response.data.has_more || false)
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail 
        || err.response?.data?.message 
        || err.message 
        || `Failed to scrape more links: ${err.response?.statusText || err.response?.status || 'Unknown error'}`
      setError(errorMessage)
    } finally {
      setScrapingMore(false)
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
      // Step 2: Save selected URLs to chosen_seeds.ndjson
      const selectedUrlsArray = Array.from(selectedUrls)
      const selectedResults = searchResults.filter(r => selectedUrlsArray.includes(r.url))
      
      await api.post('/scraper/save-seeds', {
        urls: selectedUrlsArray,
        titles: selectedResults.map(r => r.title),
        queries: selectedResults.map(r => r.query)
      })

      // Step 3: Scrape from chosen_seeds.ndjson
      const response = await api.post('/scraper/scrape-seeds', {
        topic: topic.trim() || null,
        data_specification: topic.trim() || null
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
              placeholder="e.g., restaurants in Vancouver with phone number and address"
              className="w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#5E60F8] focus:border-[#5E60F8] transition-colors"
              disabled={loading}
            />
            <p className="mt-1 text-sm text-[#64748B]">
              Describe what you're searching for and include the data fields you want extracted (e.g., phone number, email, address, contact info)
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
                Searching and scraping...
              </>
            ) : (
              <>
                <Search className="h-5 w-5" />
                Search & Scrape Automatically
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
                  {totalAvailableLinks !== null && (
                    <span className="ml-2">
                      • {totalAvailableLinks} total link{totalAvailableLinks !== 1 ? 's' : ''} available
                    </span>
                  )}
                </p>
                {totalAvailableLinks !== null && (
                  <div className="mt-2 bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-sm text-blue-900">
                      <strong>Note:</strong> We scraped the top 10 links (confidence ≥ 0.95) to get you results quickly.
                      {hasMoreLinks && (
                        <span className="block mt-1">
                          You can scrape more links below if needed.
                        </span>
                      )}
                    </p>
                  </div>
                )}
              </div>
              <button
                onClick={() => {
                  setStep('input')
                  setSearchResults([])
                  setSelectedUrls(new Set())
                  setScrapedData([])
                  setTotalAvailableLinks(null)
                  setHasMoreLinks(false)
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

            {/* Summary of data extraction results */}
            {topic && (() => {
              // Filter out failed entities (http_error, etc.)
              const successfulEntities = scrapedData.filter(item => 
                item.scraped_status === 'ok' && item.llm_payload
              )
              
              const failedEntities = scrapedData.filter(item => item.scraped_status !== 'ok')
              
              const requestedFields = detectRequestedFields(topic)
              
              // Count entities that have ALL requested fields (only from successful ones)
              const entitiesWithData = successfulEntities.filter(item => {
                // Entity has data only if ALL requested fields are present
                return requestedFields.every(field => {
                  const value = item.llm_payload[field]
                  return value !== null && value !== undefined && 
                         !(Array.isArray(value) && value.length === 0) &&
                         !(typeof value === 'string' && value.trim() === '')
                })
              }).length
              
              const entitiesWithMissing = successfulEntities.length - entitiesWithData
              
              if (scrapedData.length > 0) {
                return (
                  <>
                    <div className={`border rounded-lg p-4 mb-4 ${
                      entitiesWithData > 0 
                        ? 'bg-green-50 border-green-200' 
                        : 'bg-amber-50 border-amber-200'
                    }`}>
                      <div className="flex items-start gap-2">
                        <span className={entitiesWithData > 0 ? 'text-green-600' : 'text-amber-600'}>
                          {entitiesWithData > 0 ? '✅' : '⚠️'}
                        </span>
                        <div>
                          <p className={`text-sm font-medium ${
                            entitiesWithData > 0 ? 'text-green-900' : 'text-amber-900'
                          }`}>
                            {entitiesWithData} of {successfulEntities.length} entities have the requested data
                            {entitiesWithMissing > 0 && (
                              <span className="text-amber-700"> ({entitiesWithMissing} missing)</span>
                            )}
                            {failedEntities.length > 0 && (
                              <span className="text-gray-600"> • {failedEntities.length} failed to load</span>
                            )}
                          </p>
                          <p className={`text-xs mt-1 ${
                            entitiesWithData > 0 ? 'text-green-700' : 'text-amber-700'
                          }`}>
                            Requested: "{topic}"
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    {/* Show failed URLs in collapsed section */}
                    {failedEntities.length > 0 && (
                      <details className="mb-4 border border-gray-200 rounded-lg p-3 bg-gray-50">
                        <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800 font-medium">
                          {failedEntities.length} URL{failedEntities.length !== 1 ? 's' : ''} failed to load (click to view)
                        </summary>
                        <div className="mt-3 space-y-2 pl-4 border-l-2 border-gray-300">
                          {failedEntities.map((item, idx) => (
                            <div key={idx} className="text-xs text-gray-600 py-1">
                              <a 
                                href={item.url} 
                                target="_blank" 
                                rel="noopener noreferrer" 
                                className="text-blue-600 hover:underline break-all"
                              >
                                {item.url}
                              </a>
                              <span className="ml-2 text-gray-500">({item.scraped_status})</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </>
                )
              }
              return null
            })()}

            <div className="space-y-4">
              {scrapedData
                .filter(item => item.scraped_status === 'ok' && item.llm_payload)
                .map((item, idx) => (
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
                    {topic && item.llm_payload && (() => {
                      const missing = getMissingFields(topic, item.llm_payload)
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
                        {((topic && detectRequestedFields(topic).includes('contact_email')) || 
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
                        {/* Phone - show if requested or if exists */}
                        {((topic && detectRequestedFields(topic).includes('phone')) || 
                          item.llm_payload.phone) && (
                          <div>
                            <span className="font-medium text-[#0F172A]">Phone:</span>{' '}
                            {item.llm_payload.phone ? (
                              <a 
                                href={`tel:${item.llm_payload.phone}`}
                                className="text-[#5E60F8] hover:text-[#D946EF] hover:underline"
                              >
                                {item.llm_payload.phone}
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

            {/* Scrape More Button */}
            {hasMoreLinks && (
              <div className="mt-6 pt-6 border-t border-slate-200">
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
                  <p className="text-sm text-amber-900 mb-2">
                    <strong>More links available!</strong> You can scrape additional links to get more data.
                  </p>
                  {totalAvailableLinks !== null && (
                    <p className="text-xs text-amber-700">
                      Currently showing {scrapedData.length} of {totalAvailableLinks} available links.
                    </p>
                  )}
                </div>
                <button
                  onClick={handleScrapeMore}
                  disabled={scrapingMore}
                  className="w-full bg-gradient-to-r from-amber-600 to-orange-600 text-white px-6 py-3 rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 font-medium"
                >
                  {scrapingMore ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      Scraping more links...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-5 w-5" />
                      Scrape Next 10 Links
                    </>
                  )}
                </button>
              </div>
            )}

            {!hasMoreLinks && totalAvailableLinks !== null && totalAvailableLinks > 0 && (
              <div className="mt-6 pt-6 border-t border-slate-200">
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <p className="text-sm text-green-900">
                    ✅ All available links have been scraped! ({scrapedData.length} total)
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

