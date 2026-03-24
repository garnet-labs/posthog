import { useState } from 'react'

import { IconEllipsis } from '@posthog/icons'
import { LemonBadge, LemonCheckbox, LemonDivider, LemonMenu } from '@posthog/lemon-ui'

import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { Tooltip } from 'lib/lemon-ui/Tooltip'

import { ChartDisplayCategory } from '~/types'

import { MathSelector } from './MathSelector'
import { MathAvailability } from './types'

interface ActionFilterRowMenuProps {
    index: number
    isTrendsContext: boolean
    isFunnelContext: boolean
    isStepOptional: (step: number) => boolean
    math?: string
    mathGroupTypeIndex?: number | null
    mathAvailability: MathAvailability
    trendsDisplayCategory: ChartDisplayCategory | null
    readOnly: boolean
    query: Record<string, unknown>
    filter: { optionalInFunnel?: boolean }
    hideRename: boolean
    hideDuplicate: boolean
    hideDeleteBtn: boolean
    singleFilter: boolean
    onMathSelect: (index: number, value: string | undefined) => void
    onUpdateOptional: (checked: boolean) => void
    renameRowButton: JSX.Element
    duplicateRowButton: JSX.Element
    deleteButton: JSX.Element
}

export function ActionFilterRowMenu({
    index,
    isTrendsContext,
    isFunnelContext,
    isStepOptional,
    math,
    mathGroupTypeIndex,
    mathAvailability,
    trendsDisplayCategory,
    readOnly,
    query,
    filter,
    hideRename,
    hideDuplicate,
    hideDeleteBtn,
    singleFilter,
    onMathSelect,
    onUpdateOptional,
    renameRowButton,
    duplicateRowButton,
    deleteButton,
}: ActionFilterRowMenuProps): JSX.Element {
    const [isMenuVisible, setIsMenuVisible] = useState(false)

    const wrapWithClose = (element: JSX.Element): JSX.Element => (
        <div onClick={() => setIsMenuVisible(false)}>{element}</div>
    )

    return (
        <div className="relative">
            <LemonMenu
                placement={isTrendsContext ? 'bottom-end' : 'bottom-start'}
                visible={isMenuVisible}
                closeOnClickInside={false}
                onVisibilityChange={setIsMenuVisible}
                items={[
                    // MathSelector for funnels only (trends shows it inline)
                    ...(isFunnelContext
                        ? [
                              {
                                  label: () => (
                                      <>
                                          <MathSelector
                                              math={math}
                                              mathGroupTypeIndex={mathGroupTypeIndex}
                                              index={index}
                                              onMathSelect={onMathSelect}
                                              disabled={readOnly}
                                              style={{
                                                  maxWidth: '100%',
                                                  width: 'initial',
                                              }}
                                              mathAvailability={mathAvailability}
                                              trendsDisplayCategory={trendsDisplayCategory}
                                              query={query}
                                          />
                                          <LemonDivider />
                                      </>
                                  ),
                              },
                          ]
                        : []),
                    // Optional step checkbox for funnels only
                    ...(isFunnelContext && index > 0
                        ? [
                              {
                                  label: () => (
                                      <>
                                          <Tooltip title="Optional steps show conversion rates from the last mandatory step, but are not necessary to move to the next step in the funnel">
                                              <div className="px-2 py-1">
                                                  <LemonCheckbox
                                                      checked={!!filter.optionalInFunnel}
                                                      onChange={(checked) => {
                                                          onUpdateOptional(checked)
                                                      }}
                                                      label="Optional step"
                                                  />
                                              </div>
                                          </Tooltip>
                                          <LemonDivider />
                                      </>
                                  ),
                              },
                          ]
                        : []),
                    ...(!hideRename
                        ? [
                              {
                                  label: () => wrapWithClose(renameRowButton),
                              },
                          ]
                        : []),
                    ...(!hideDuplicate && !singleFilter
                        ? [
                              {
                                  label: () => wrapWithClose(duplicateRowButton),
                              },
                          ]
                        : []),
                    ...(!hideDeleteBtn && !singleFilter
                        ? [
                              {
                                  label: () => wrapWithClose(deleteButton),
                              },
                          ]
                        : []),
                ]}
            >
                <LemonButton
                    size="medium"
                    aria-label="Show more actions"
                    data-attr={`more-button-${index}`}
                    icon={<IconEllipsis />}
                    noPadding
                />
            </LemonMenu>
            <LemonBadge
                position="top-right"
                size="small"
                visible={isFunnelContext && (math != null || isStepOptional(index + 1))}
            />
        </div>
    )
}
