import type { ProductLabel } from '../lib/types'
import { formatDateTime, licenceLabel } from '../lib/format'
import { ProvenanceList } from './ProvenanceList'
import { Alert, Badge, EmptyState, ExternalLink, Panel, SectionHeading } from './ui'

export const PRODUCT_LABEL_WARNING =
  'Manufacturer label information — not clinical evidence, not a HerbaGuard finding. Licence unverified.'

export function ProductLabelsPanel({
  labels,
  total,
}: {
  labels: ProductLabel[]
  total?: number
}) {
  return (
    <section
      aria-label="Product labels (NIH DSLD)"
      className="bg-hatch space-y-5 rounded-2xl border-2 border-dashed border-clay-600/40 bg-clay-50/60 p-5 sm:p-6"
    >
      <SectionHeading
        eyebrow="Supplementary source"
        title="Product labels (NIH DSLD)"
        description="Stored manufacturer labels that list this plant by an exact, resolved ingredient name. They describe products, not study findings."
        action={total !== undefined ? <Badge>{total} labels matched</Badge> : null}
      />

      <Alert tone="warn" title="Product-label information">
        <p>{PRODUCT_LABEL_WARNING}</p>
        <p className="mt-2 text-xs">
          These labels are not evidence of an interaction, efficacy or safety, and a missing product
          is not evidence of safety. Manufacturer wording may be marketing or precautionary text and
          is not HerbaGuard's advice. Do not republish this content until the source licence is
          verified.
        </p>
      </Alert>

      {labels.length === 0 ? (
        <EmptyState title="No NIH DSLD label matched this plant">
          <p>
            No stored product label lists this plant by an exact, resolved ingredient name. This is
            a coverage statement only; it does not show that products containing this plant are safe
            or free of interactions.
          </p>
        </EmptyState>
      ) : (
        <ul className="grid gap-4 2xl:grid-cols-2">
          {labels.map((label) => (
            <li key={label.dsld_id}>
              <Panel as="article" className="h-full border-l-4 border-l-clay-600/60">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold text-ink">
                      {label.product_name ?? `DSLD product ${label.dsld_id}`}
                    </h3>
                    <p className="text-sm text-muted">
                      {label.brand ? `${label.brand} · ` : ''}DSLD ID {label.dsld_id}
                    </p>
                  </div>
                  <Badge tone="warn">{licenceLabel(label.licence_status)}</Badge>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {label.market_status ? <Badge>{label.market_status}</Badge> : null}
                  {label.upc ? <Badge>UPC {label.upc}</Badge> : null}
                  <Badge>{label.label_statement_count} label statements</Badge>
                </div>

                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-muted">
                      Labelled ingredients matched to this plant
                    </dt>
                    <dd className="mt-1 space-y-1">
                      {label.ingredients.length > 0 ? (
                        label.ingredients.map((ingredient) => (
                          <p key={`${ingredient.ingredient}-${ingredient.amount_per_serving}`}>
                            <span className="font-medium">{ingredient.ingredient}</span>
                            {ingredient.amount_per_serving
                              ? ` — ${ingredient.amount_per_serving}${ingredient.unit ? ` ${ingredient.unit}` : ''} per serving`
                              : ' — amount not stated'}
                            {ingredient.category ? (
                              <span className="text-muted"> ({ingredient.category})</span>
                            ) : null}
                          </p>
                        ))
                      ) : (
                        <p className="text-muted">Ingredient row not stated.</p>
                      )}
                    </dd>
                  </div>
                </dl>

                {label.precautions.length > 0 ? (
                  <div className="mt-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted">
                      Manufacturer “Precautions” statements
                    </p>
                    <ul className="mt-1 space-y-2">
                      {label.precautions.map((precaution) => (
                        <li
                          key={precaution}
                          className="rounded-r-md border-l-4 border-clay-600/50 bg-clay-50 p-2.5 font-display text-[15px] text-clay-800"
                        >
                          “{precaution}”
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted">
                    No “Precautions” statement is stored for this label.
                  </p>
                )}

                <p className="mt-3 text-xs text-muted">
                  Label URL:{' '}
                  <ExternalLink href={label.label_url}>
                    {label.label_url ?? 'not stored'}
                  </ExternalLink>
                  {label.provenance[0] ? (
                    <>
                      {' '}
                      · retrieved {formatDateTime(label.provenance[0].retrieved_at)}
                    </>
                  ) : null}
                </p>
                <ProvenanceList items={label.provenance} compact />
              </Panel>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
