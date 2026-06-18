import { ReactNode, useEffect, useLayoutEffect, useRef, useState } from 'react'

type Props<T> = {
  items: T[]
  itemHeight: number
  overscan?: number
  renderItem: (item: T, index: number) => ReactNode
  getKey: (item: T, index: number) => string | number
  className?: string
  /** Activate virtualization only when items.length exceeds this count. */
  threshold?: number
}

/**
 * Minimal fixed-size virtualization. Renders only rows visible in viewport
 * plus `overscan` (default 6) above/below. No external deps.
 *
 * Requires each row to be exactly `itemHeight` px (use `box-sizing: border-box`
 * + explicit height in CSS to guarantee uniformity).
 */
export function VirtualList<T>({
  items,
  itemHeight,
  overscan = 6,
  renderItem,
  getKey,
  className,
  threshold = 80,
}: Props<T>) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewport, setViewport] = useState(0)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    setViewport(el.clientHeight)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setViewport(entry.contentRect.height)
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Fall back to plain rendering for small lists — avoids absolute positioning
  // overhead and lets the browser handle short scrolls naturally.
  if (items.length <= threshold) {
    return (
      <div ref={containerRef} className={className}>
        {items.map((item, idx) => (
          <div key={getKey(item, idx)} style={{ height: itemHeight, boxSizing: 'border-box' }}>
            {renderItem(item, idx)}
          </div>
        ))}
      </div>
    )
  }

  const total = items.length * itemHeight
  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
  const end = Math.min(
    items.length,
    Math.ceil((scrollTop + (viewport || itemHeight * overscan * 4)) / itemHeight) + overscan,
  )
  const slice = items.slice(start, end)
  const offset = start * itemHeight

  return (
    <div
      ref={containerRef}
      className={className}
      onScroll={(e) => setScrollTop((e.currentTarget as HTMLDivElement).scrollTop)}
    >
      <div style={{ height: total, position: 'relative' }}>
        <div style={{ position: 'absolute', top: offset, left: 0, right: 0 }}>
          {slice.map((item, i) => {
            const idx = start + i
            return (
              <div key={getKey(item, idx)} style={{ height: itemHeight, boxSizing: 'border-box' }}>
                {renderItem(item, idx)}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
