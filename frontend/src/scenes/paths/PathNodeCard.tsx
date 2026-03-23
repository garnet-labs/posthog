import { useActions, useValues } from 'kea'
import { useRef, useState } from 'react'

import { Popover } from 'lib/lemon-ui/Popover/Popover'

import { FunnelPathsFilter } from '~/queries/schema/schema-general'
import { InsightLogicProps } from '~/types'

import { PATH_NODE_CARD_LEFT_OFFSET, PATH_NODE_CARD_WIDTH } from './constants'
import { PathNodeCardButton } from './PathNodeCardButton'
import { PathNodeCardMenu } from './PathNodeCardMenu'
import { pathsDataLogic } from './pathsDataLogic'
import { PathNodeData, calculatePathNodeCardTop, isSelectedPathStartOrEnd, pageUrl } from './pathUtils'

export type PathNodeCardProps = {
    insightProps: InsightLogicProps
    node: PathNodeData
    canvasHeight: number
}

export function PathNodeCard({ insightProps, node, canvasHeight }: PathNodeCardProps): JSX.Element | null {
    const { pathsFilter: _pathsFilter, funnelPathsFilter: _funnelPathsFilter } = useValues(pathsDataLogic(insightProps))
    const { updateInsightFilter, openPersonsModal, viewPathToFunnel } = useActions(pathsDataLogic(insightProps))

    const pathsFilter = _pathsFilter || {}
    const funnelPathsFilter = _funnelPathsFilter || ({} as FunnelPathsFilter)

    const [isCardHovered, setIsCardHovered] = useState(false)
    const [isPopoverHovered, setIsPopoverHovered] = useState(false)
    const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const showPopover = isCardHovered || isPopoverHovered

    const clearHideTimeout = (): void => {
        if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current)
            hideTimeoutRef.current = null
        }
    }

    const scheduleHide = (setter: (v: boolean) => void): void => {
        hideTimeoutRef.current = setTimeout(() => setter(false), 100)
    }

    if (!node.visible) {
        return null
    }

    const isPathStart = node.targetLinks.length === 0
    const isPathEnd = node.sourceLinks.length === 0
    const continuingCount = node.sourceLinks.reduce((prev, curr) => prev + curr.value, 0)
    const dropOffCount = node.value - continuingCount
    const averageConversionTime = !isPathStart
        ? node.targetLinks.reduce((prev, curr) => prev + curr.average_conversion_time / 1000, 0) /
          node.targetLinks.length
        : null

    return (
        <Popover
            visible={showPopover}
            overlay={
                <PathNodeCardMenu
                    name={node.name}
                    count={node.value}
                    continuingCount={continuingCount}
                    dropOffCount={dropOffCount}
                    averageConversionTime={averageConversionTime}
                    isPathStart={isPathStart}
                    isPathEnd={isPathEnd}
                    openPersonsModal={openPersonsModal}
                    data-attr="path-node-card-popover"
                />
            }
            placement="bottom"
            padded={false}
            matchWidth
            onMouseEnterInside={() => {
                clearHideTimeout()
                setIsPopoverHovered(true)
            }}
            onMouseLeaveInside={() => {
                scheduleHide(setIsPopoverHovered)
            }}
            className="PathNodeCard__popover"
        >
            <div
                className="absolute rounded bg-surface-primary p-1"
                // eslint-disable-next-line react/forbid-dom-props
                style={{
                    width: PATH_NODE_CARD_WIDTH,
                    left: !isPathEnd
                        ? node.x0 + PATH_NODE_CARD_LEFT_OFFSET
                        : node.x0 + PATH_NODE_CARD_LEFT_OFFSET - PATH_NODE_CARD_WIDTH,
                    top: calculatePathNodeCardTop(node, canvasHeight),
                    border: `1px solid ${
                        isSelectedPathStartOrEnd(pathsFilter, funnelPathsFilter, node)
                            ? 'purple'
                            : 'var(--color-border-primary)'
                    }`,
                }}
                data-attr="path-node-card"
                onMouseEnter={() => {
                    clearHideTimeout()
                    setIsCardHovered(true)
                }}
                onMouseLeave={() => {
                    scheduleHide(setIsCardHovered)
                }}
            >
                <PathNodeCardButton
                    name={node.name}
                    count={node.value}
                    node={node}
                    viewPathToFunnel={viewPathToFunnel}
                    openPersonsModal={openPersonsModal}
                    setFilter={updateInsightFilter}
                    filter={pathsFilter}
                    showFullUrls={pathsFilter.showFullUrls}
                    tooltipContent={pageUrl(node, true, true)}
                />
            </div>
        </Popover>
    )
}
