type CacheEntry<T> = {
  data: T
  timestamp: number
}

const cache = new Map<string, CacheEntry<unknown>>()
const CACHE_TTL = 10 * 60 * 1000 // 10 minutes

export function getCachedData<T>(key: string): T | null {
  const entry = cache.get(key) as CacheEntry<T> | undefined
  if (!entry) return null
  
  const isExpired = Date.now() - entry.timestamp > CACHE_TTL
  if (isExpired) {
    cache.delete(key)
    return null
  }
  
  return entry.data
}

export function setCachedData<T>(key: string, data: T): void {
  cache.set(key, {
    data,
    timestamp: Date.now()
  })
}

export function invalidateCache(key: string): void {
  cache.delete(key)
}

export function invalidateCacheByPrefix(prefix: string): void {
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) {
      cache.delete(key)
    }
  }
}
