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
    
    // Debug: Log what we're detecting (disabled for production)
    // console.log('[DEBUG] Detecting fields from prompt:', dataSpec)
    
    // Field mapping with flexible keyword matching
    // Note: Order matters - more specific matches should come first
    // Use word boundaries to avoid false positives (e.g., "iPhone" shouldn't match "phone")
    const fieldMappings: { [key: string]: string[] } = {
      'opening_hours': ['opening hours', 'opening time', 'business hours', 'operating hours', 'when open', 'schedule', 'hours of operation', 'opening schedule', 'what time', 'what times'],
      'contact_email': ['email', 'contact email', 'e-mail', 'mail', 'contact', 'correspondence'],
      'phone': ['phone number', 'telephone', 'tel', 'call'], // Removed 'phone' alone to avoid matching "iPhone"
      'address': ['address', 'location', 'street', 'postal'],
      'city': ['city', 'town'],
      'country': ['country', 'nation'],
      'website': ['website', 'site', 'url', 'web', 'homepage'],
      'description': ['description', 'details', 'info', 'information', 'about', 'specs', 'specifications'],
      'category': ['category', 'type', 'kind', 'genre'],
      'storage': ['storage', 'capacity', 'gb', 'tb', 'memory'],
      'colors': ['color', 'colors', 'colour', 'colours', 'available colors'],
      'tags': ['tags', 'tag', 'keywords', 'features'],
      'genres': ['genre', 'genres'],
      'reading_period': ['reading period', 'submission period', 'deadline', 'window'],
      'reading_fee': ['reading fee', 'submission fee', 'submission cost'], // Only for literary magazine submission fees
      'price': ['price', 'prices', 'pricing', 'how much', 'dollar', 'dollars', '$', 'cost of', 'costs of', 'what does it cost'], // Product/service prices - removed standalone 'cost'/'costs' to avoid false matches
      'price_numeric': ['price', 'prices', 'pricing', 'how much', 'dollar', 'dollars', '$', 'cost of', 'costs of', 'what does it cost'], // Numeric price value
      'submission_methods': ['submission', 'submit', 'guideline', 'how to submit', 'method'],
      'response_time': ['response', 'reply', 'answer time', 'turnaround'],
      'name': ['name', 'title', 'company', 'organization']
    }
    
    // Check each field mapping with word boundary matching for single words
    // Process multi-word phrases first (more specific) to avoid false matches
    Object.keys(fieldMappings).forEach(field => {
      const keywords = fieldMappings[field]
      
      // First check multi-word phrases (more specific)
      const multiWordKeywords = keywords.filter(k => k.includes(' '))
      const singleWordKeywords = keywords.filter(k => !k.includes(' '))
      
      let matches = false
      
      // Check multi-word phrases first
      if (multiWordKeywords.length > 0) {
        matches = multiWordKeywords.some(keyword => specLower.includes(keyword))
      }
      
      // Only check single words if no multi-word match found (to avoid false positives)
      if (!matches && singleWordKeywords.length > 0) {
        matches = singleWordKeywords.some(keyword => {
          // Special handling for symbols like $ - they should match literally, not as regex anchors
          if (keyword === '$') {
            // For $ symbol, check if it actually appears in the text (not as regex end anchor)
            const result = specLower.includes('$')
            if (result && (field === 'price' || field === 'price_numeric')) {
              console.log(`[DEBUG] Price keyword "$" matched in: "${specLower}"`)
            }
            return result
          }
          
          // For other keywords, escape regex special characters and use word boundaries
          const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
          const wordBoundaryRegex = new RegExp(`\\b${escapedKeyword}\\b`, 'i')
          const result = wordBoundaryRegex.test(specLower)
          if (result && (field === 'price' || field === 'price_numeric')) {
            console.log(`[DEBUG] Price keyword "${keyword}" matched in: "${specLower}"`)
          }
          return result
        })
      }
      
      // CRITICAL: For price fields, require explicit confirmation even if a keyword matched
      if (matches && (field === 'price' || field === 'price_numeric')) {
        // Double-check that price-related keywords are actually present
        const priceKeywords = ['price', 'prices', 'pricing', 'how much', 'dollar', 'dollars', '$', 'cost of', 'costs of', 'what does it cost']
        const hasExplicitPriceKeyword = priceKeywords.some(keyword => {
          if (keyword.includes(' ')) {
            return specLower.includes(keyword)
          }
          const regex = new RegExp(`\\b${keyword}\\b`, 'i')
          return regex.test(specLower)
        })
          if (!hasExplicitPriceKeyword) {
            // console.log(`[DEBUG] Price field "${field}" matched but no explicit price keyword found, skipping`)
            matches = false // Prevent adding price field
          }
      }
      
      if (matches && !requestedFields.includes(field)) {
        requestedFields.push(field)
      }
    })
    
    // console.log('[DEBUG] Final detected fields:', requestedFields)
    return requestedFields
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
      // Use the automatic endpoint that does: search -> classify -> filter (confidence >= 0.95) -> scrape all filtered results
      const response = await api.post('/scraper/search-and-scrape-auto', {
        topic: topic.trim(),
        data_specification: null  // Don't duplicate topic - topic already contains the full request
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
        data_specification: null  // Don't duplicate topic
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
        data_specification: null  // Don't duplicate topic
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
                      <strong>Note:</strong> We scraped all links with confidence ≥ 0.95 (matching terminal workflow).
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
            {topic && scrapedData.length > 0 && (
              <>
                <div className="border rounded-lg p-4 mb-4 bg-blue-50 border-blue-200">
                  <p className="text-sm text-blue-900">
                    <span className="font-medium">Requested:</span> "{topic}"
                  </p>
                </div>
                
                {/* Show failed URLs in collapsed section */}
                {(() => {
                  const failedEntities = scrapedData.filter(item => item.scraped_status !== 'ok')
                  return failedEntities.length > 0 ? (
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
                  ) : null
                })()}
              </>
            )}

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
                  </div>
                  
                  {item.llm_payload ? (
                    <div className="space-y-3">
                      <h3 className="font-semibold text-lg text-[#0F172A]">
                        {item.llm_payload.name || 'Unnamed Entity'}
                      </h3>
                      
                      {/* Smart field rendering - show only requested fields + essential context */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                        {(() => {
                          // Get what user requested from the topic
                          const requestedFields = topic ? detectRequestedFields(topic) : []
                          
                          // Fields to always exclude (metadata/internal)
                          const excludeFields = ['name', 'error', 'extra', 'notes']
                          
                          // Essential context fields that are always shown (if available)
                          const essentialContextFields = ['website', 'description', 'category']
                          
                          // Smart field relationships - if user asks for X, also show related Y
                          const fieldRelationships: { [key: string]: string[] } = {
                            'price': ['storage', 'colors', 'category'], // If asking for price, also show storage/colors (pricing variants)
                            'price_numeric': ['storage', 'colors', 'category'],
                            'contact_email': ['phone', 'address'], // If asking for email, also show phone/address
                            'phone': ['contact_email', 'address'],
                            'address': ['city', 'country', 'phone', 'contact_email'],
                            'city': ['country', 'address'],
                            'country': ['city', 'address']
                          }
                          
                          // Determine which fields to show
                          let fieldsToShow = new Set<string>()
                          
                          if (requestedFields.length > 0) {
                            // User specified what they want - show only requested + related + minimal context
                            requestedFields.forEach(field => {
                              fieldsToShow.add(field)
                              // Add related fields
                              if (fieldRelationships[field]) {
                                fieldRelationships[field].forEach(related => fieldsToShow.add(related))
                              }
                            })
                            // Add minimal essential context (just website for source reference)
                            fieldsToShow.add('website')
                          } else {
                            // No specific fields requested - show essential fields only (smart defaults)
                            const defaultFields = ['price', 'price_numeric', 'description', 'category', 'website', 'storage', 'colors']
                            defaultFields.forEach(field => fieldsToShow.add(field))
                          }
                          
                          // Get all fields from payload that should be displayed
                          const allFields = Object.keys(item.llm_payload)
                            .filter(key => !excludeFields.includes(key))
                            .filter(key => {
                              // Only show if it's in fieldsToShow set
                              if (fieldsToShow.size > 0 && !fieldsToShow.has(key)) {
                                return false
                              }
                              
                              const value = item.llm_payload[key]
                              // Exclude null, undefined, empty strings, empty arrays, and zero price_numeric
                              if (value === null || value === undefined) return false
                              if (typeof value === 'string' && value.trim() === '') return false
                              if (Array.isArray(value) && value.length === 0) return false
                              if (key === 'price_numeric' && value === 0) return false
                              return true
                            })
                          
                          // Sort: requested fields first, then essential context, then others
                          const sortedFields = allFields.sort((a, b) => {
                            const aRequested = requestedFields.includes(a)
                            const bRequested = requestedFields.includes(b)
                            if (aRequested && !bRequested) return -1
                            if (!aRequested && bRequested) return 1
                            
                            const aEssential = essentialContextFields.includes(a)
                            const bEssential = essentialContextFields.includes(b)
                            if (aEssential && !bEssential) return -1
                            if (!aEssential && bEssential) return 1
                            
                            return a.localeCompare(b)
                          })
                          
                          return sortedFields
                            .filter(field => {
                              // Skip price_numeric if price already exists (to avoid duplicates)
                              return !(field === 'price_numeric' && item.llm_payload.price)
                            })
                            .map((field) => {
                            const value = item.llm_payload[field]
                            
                            // Format field name for display
                            const fieldLabel = field.split('_').map(w => 
                              w.charAt(0).toUpperCase() + w.slice(1)
                            ).join(' ')
                            
                            // Special handling for different field types
                            if (field === 'price' || field === 'price_numeric') {
                              // Price fields - always show if exists
                              let priceValue: string | null = null
                              if (field === 'price') {
                                priceValue = value as string
                              } else if (field === 'price_numeric' && typeof value === 'number' && value > 0) {
                                priceValue = `$${value.toLocaleString()}`
                              }
                              
                              return (
                                <div key={field}>
                                  <span className="font-medium text-[#0F172A]">Price:</span>{' '}
                                  {priceValue ? (
                                    <span className="text-[#64748B]">{priceValue}</span>
                                  ) : (
                                    <span className="text-amber-600 italic text-xs">Not found</span>
                                  )}
                                </div>
                              )
                            }
                            
                            if (field === 'website') {
                              return (
                                <div key={field}>
                                  <span className="font-medium text-[#0F172A]">Website:</span>{' '}
                                  <a 
                                    href={value as string} 
                                    target="_blank"
                                    rel="noopener noreferrer" 
                                    className="text-[#5E60F8] hover:text-[#D946EF] hover:underline break-all"
                                  >
                                    {value as string}
                                  </a>
                                </div>
                              )
                            }
                            
                            if (field === 'contact_email' || field === 'email') {
                              return (
                                <div key={field}>
                                  <span className="font-medium text-[#0F172A]">Email:</span>{' '}
                                  <a 
                                    href={`mailto:${value}`}
                                    className="text-[#5E60F8] hover:text-[#D946EF] hover:underline"
                                  >
                                    {value as string}
                                  </a>
                                </div>
                              )
                            }
                            
                            if (field === 'phone') {
                              return (
                                <div key={field}>
                                  <span className="font-medium text-[#0F172A]">Phone:</span>{' '}
                                  <a 
                                    href={`tel:${value}`}
                                    className="text-[#5E60F8] hover:text-[#D946EF] hover:underline"
                                  >
                                    {value as string}
                                  </a>
                                </div>
                              )
                            }
                            
                            if (Array.isArray(value)) {
                              return (
                                <div key={field}>
                                  <span className="font-medium text-[#0F172A]">{fieldLabel}:</span>{' '}
                                  <span className="text-[#64748B]">
                                    {value.map((item: any, i: number) => (
                                      <span key={i}>
                                        {String(item)}
                                        {i < value.length - 1 ? ', ' : ''}
                                      </span>
                                    ))}
                                  </span>
                                </div>
                              )
                            }
                            
                            // Default: render as text
                            return (
                              <div key={field}>
                                <span className="font-medium text-[#0F172A]">{fieldLabel}:</span>{' '}
                                <span className="text-[#64748B]">{String(value)}</span>
                              </div>
                            )
                          })
                        })()}
                      </div>
                      
                      {/* Show extra/notes field separately if it exists and is relevant */}
                      {(() => {
                        const requestedFields = topic ? detectRequestedFields(topic) : []
                        const hasExtra = item.llm_payload.extra || item.llm_payload.notes
                        
                        // Show extra/notes if:
                        // 1. No specific fields requested (general query), OR
                        // 2. Extra info might be relevant to requested fields
                        const extraText = (item.llm_payload.extra || item.llm_payload.notes || '').toLowerCase()
                        const shouldShowExtra = hasExtra && (
                          requestedFields.length === 0 || 
                          (requestedFields.includes('opening_hours') && (
                            extraText.includes('hour') || extraText.includes('open') || extraText.includes('close') || extraText.includes('time')
                          )) ||
                          (requestedFields.includes('price') || requestedFields.includes('price_numeric')) && (
                            extraText.includes('price') || extraText.includes('cost')
                          )
                        )
                        
                        return shouldShowExtra ? (
                          <div className="mt-3 pt-3 border-t border-slate-200">
                            <span className="font-medium text-[#0F172A]">Additional Info:</span>{' '}
                            <span className="text-sm text-[#64748B]">
                              {item.llm_payload.extra || item.llm_payload.notes}
                            </span>
                          </div>
                        ) : null
                      })()}
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
                      Scrape Next 5 Links
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

