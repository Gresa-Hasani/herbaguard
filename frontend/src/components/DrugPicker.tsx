import { useState } from 'react'

import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useDrugSearch } from '../hooks/useApi'
import type { Drug } from '../lib/types'
import { Icon } from './icons'
import { Badge, Spinner } from './ui'

const MAX_DRUGS = 5

export function DrugPicker({
  selected,
  onChange,
}: {
  selected: Drug[]
  onChange: (drugs: Drug[]) => void
}) {
  const [query, setQuery] = useState('')
  const debounced = useDebouncedValue(query)
  const { data, isFetching, isError } = useDrugSearch(debounced)

  function add(drug: Drug) {
    if (selected.some((item) => item.rxcui === drug.rxcui) || selected.length >= MAX_DRUGS) return
    onChange([...selected, drug])
    setQuery('')
  }

  function remove(rxcui: string) {
    onChange(selected.filter((item) => item.rxcui !== rxcui))
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor="drug-search" className="block text-sm font-semibold text-ink">
          Search medications
        </label>
        <span className="rounded-full bg-surface-3 px-2 py-0.5 text-xs font-medium text-ink-soft">
          {selected.length}/{MAX_DRUGS} selected
        </span>
      </div>

      {selected.length > 0 ? (
        <ul className="mt-2.5 flex flex-wrap gap-2" aria-label="Selected medications">
          {selected.map((drug) => (
            <li key={drug.rxcui} className="animate-pop">
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-forest-600/30 bg-forest-50 py-1 pl-2.5 pr-1 text-sm font-medium text-forest-900">
                <Icon name="pill" className="h-3.5 w-3.5 text-forest-600" />
                {drug.name}
                <button
                  type="button"
                  onClick={() => remove(drug.rxcui)}
                  aria-label={`Remove ${drug.name}`}
                  className="rounded-md p-1 text-forest-700 transition-colors hover:bg-forest-100"
                >
                  <Icon name="x" className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="relative mt-2">
        <Icon
          name="search"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        />
        <input
          id="drug-search"
          type="search"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={selected.length >= MAX_DRUGS}
          placeholder={
            selected.length >= MAX_DRUGS
              ? 'Maximum of five medications'
              : 'e.g. warfarin, sertraline'
          }
          className="w-full rounded-lg border border-line-strong bg-surface py-2.5 pl-9 pr-3 text-sm text-ink shadow-soft transition-shadow placeholder:text-muted/70 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/15 disabled:bg-surface-2"
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Search is limited to the HerbaGuard drug index; unknown brand names are not sent to an
        external service.
      </p>

      <div className="scrollbar-thin mt-2 max-h-60 overflow-y-auto rounded-lg border border-line bg-surface-2">
        {selected.length >= MAX_DRUGS ? (
          <p className="p-3 text-sm text-muted">Remove a medication to search for another.</p>
        ) : query.trim().length < 2 ? (
          <p className="p-3 text-sm text-muted">Type at least two letters to search.</p>
        ) : isFetching ? (
          <div className="p-3">
            <Spinner label="Searching medications…" />
          </div>
        ) : isError ? (
          <p className="p-3 text-sm text-danger">
            Medication search is unavailable. Please try again.
          </p>
        ) : data && data.items.length > 0 ? (
          <ul className="space-y-1 p-2">
            {data.items.map((drug) => {
              const alreadySelected = selected.some((item) => item.rxcui === drug.rxcui)
              return (
                <li key={drug.rxcui}>
                  <button
                    type="button"
                    disabled={alreadySelected}
                    onClick={() => add(drug)}
                    className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md bg-surface px-2.5 py-2 text-left text-sm shadow-soft transition-colors hover:bg-forest-50 disabled:cursor-default disabled:opacity-50"
                  >
                    <span>
                      <span className="font-medium text-ink">{drug.name}</span>
                      <span className="ml-2 text-xs text-muted">RxCUI {drug.rxcui}</span>
                    </span>
                    <span className="flex flex-wrap gap-1">
                      {drug.atc_classes.slice(0, 2).map((atc) => (
                        <Badge key={atc.code}>
                          {atc.code} · {atc.name}
                        </Badge>
                      ))}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="p-3 text-sm text-muted">
            No indexed medication matches that name. Try the generic name.
          </p>
        )}
      </div>
    </div>
  )
}
