import { useState } from 'react'

import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { usePlantSearch } from '../hooks/useApi'
import type { HerbRef } from '../lib/types'
import { Icon } from './icons'
import { Badge, Spinner } from './ui'

export function HerbPicker({
  selected,
  onSelect,
  onClear,
}: {
  selected: HerbRef | null
  onSelect: (herb: HerbRef) => void
  onClear: () => void
}) {
  const [query, setQuery] = useState('')
  const debounced = useDebouncedValue(query)
  const { data, isFetching, isError } = usePlantSearch(debounced)

  if (selected) {
    return (
      <div className="animate-pop flex items-start gap-3 rounded-xl border border-forest-600/30 bg-forest-50 p-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-forest-800 text-forest-100">
          <Icon name="leaf" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-forest-700">
            Selected herb
          </p>
          <p className="mt-0.5 font-display text-lg font-semibold leading-tight text-forest-950">
            {selected.common_name ?? selected.pharmaceutical_name}
          </p>
          <p className="text-sm text-ink-soft">
            {selected.pharmaceutical_name} · plant part: {selected.plant_part}
          </p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-md border border-forest-600/30 bg-surface px-2.5 py-1 text-xs font-semibold text-forest-700 transition-colors hover:bg-forest-100"
        >
          Change
        </button>
      </div>
    )
  }

  return (
    <div>
      <label htmlFor="herb-search" className="block text-sm font-semibold text-ink">
        Search medicinal herbs
      </label>
      <div className="relative mt-1.5">
        <Icon
          name="search"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        />
        <input
          id="herb-search"
          type="search"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. St John's wort, ginger, milk thistle"
          className="w-full rounded-lg border border-line-strong bg-surface py-2.5 pl-9 pr-3 text-sm text-ink shadow-soft transition-shadow placeholder:text-muted/70 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/15"
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Only herbs in the HerbaGuard index are shown. Type at least two letters.
      </p>

      <div className="scrollbar-thin mt-2 max-h-72 overflow-y-auto rounded-lg border border-line bg-surface-2">
        {query.trim().length < 2 ? (
          <p className="p-3 text-sm text-muted">Start typing to search the curated herb list.</p>
        ) : isFetching ? (
          <div className="p-3">
            <Spinner label="Searching herbs…" />
          </div>
        ) : isError ? (
          <p className="p-3 text-sm text-danger">Herb search is unavailable. Please try again.</p>
        ) : data && data.items.length > 0 ? (
          <ul className="divide-y divide-line">
            {data.items.map((taxon) => (
              <li key={taxon.wfo_id} className="p-2">
                <p className="px-1 text-xs text-muted">
                  <span className="italic">{taxon.scientific_name}</span>
                  {taxon.authorship ? ` ${taxon.authorship}` : ''}
                  {taxon.family ? ` · ${taxon.family}` : ''}
                </p>
                <ul className="mt-1 space-y-1">
                  {taxon.herbs.map((herb) => (
                    <li key={`${taxon.wfo_id}-${herb.pharmaceutical_name}`}>
                      <button
                        type="button"
                        onClick={() => {
                          onSelect(herb)
                          setQuery('')
                        }}
                        className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md bg-surface px-2.5 py-2 text-left text-sm shadow-soft transition-colors hover:bg-forest-50"
                      >
                        <span>
                          <span className="font-medium text-ink">
                            {herb.common_name ?? herb.pharmaceutical_name}
                          </span>
                          <span className="ml-2 text-muted">{herb.pharmaceutical_name}</span>
                        </span>
                        <Badge>{herb.plant_part}</Badge>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        ) : (
          <p className="p-3 text-sm text-muted">
            No curated herb matches that name. Common names can be ambiguous; try the scientific or
            pharmaceutical name.
          </p>
        )}
      </div>
    </div>
  )
}
