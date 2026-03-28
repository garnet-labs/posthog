import clsx from 'clsx'
import { useRef } from 'react'

import { percentage } from 'lib/utils'
import { funnelTitle } from 'scenes/trends/persons-modal/persons-modal-utils'
import { openPersonsModal } from 'scenes/trends/persons-modal/PersonsModal'

import { FunnelsActorsQuery, NodeKind, isExperimentFunnelMetric } from '~/queries/schema/schema-general'
import { FunnelStepWithConversionMetrics } from '~/types'

import { getVariantColor } from '../../utils'
import { useTooltip } from './FunnelBarVertical'
import { useFunnelChartData } from './FunnelChart'

export interface StepBarProps {
    step: FunnelStepWithConversionMetrics
    stepIndex: number
}

interface StepBarCSSProperties extends React.CSSProperties {
    '--series-color': string
    '--conversion-rate': string
}

export function StepBar({ step, stepIndex }: StepBarProps): JSX.Element {
    const ref = useRef<HTMLDivElement | null>(null)
    const { showTooltip, hideTooltip } = useTooltip()
    const { experiment, metric, funnelsQuery } = useFunnelChartData()

    const variantKey = Array.isArray(step.breakdown_value)
        ? step.breakdown_value[0]?.toString() || ''
        : step.breakdown_value?.toString() || ''

    const seriesColor =
        experiment?.parameters?.feature_flag_variants && variantKey
            ? getVariantColor(variantKey, experiment.parameters.feature_flag_variants)
            : 'var(--text-muted)'

    const handleClick = (converted: boolean): void => {
        if (!funnelsQuery || !experiment) {
            return
        }

        const stepNo = stepIndex + 1
        const orderType = metric && isExperimentFunnelMetric(metric) ? metric.funnel_order_type : undefined

        const title = funnelTitle({
            converted,
            step: stepNo,
            breakdown_value: variantKey,
            label: step.custom_name || step.name,
            seriesId: step.order,
            order_type: orderType,
        })

        const query: FunnelsActorsQuery = {
            kind: NodeKind.FunnelsActorsQuery,
            source: funnelsQuery,
            funnelStep: converted ? stepNo : -stepNo,
            funnelStepBreakdown: variantKey,
            includeRecordings: true,
        }

        openPersonsModal({
            title,
            query,
            additionalSelect: { matched_recordings: 'matched_recordings' },
        })
    }

    return (
        <>
            <div
                className={clsx('StepBar')}
                /* eslint-disable-next-line react/forbid-dom-props */
                style={
                    {
                        '--series-color': seriesColor,
                        '--conversion-rate': percentage(step.conversionRates.fromBasisStep, 1, true),
                    } as StepBarCSSProperties
                }
                ref={ref}
                onMouseEnter={() => {
                    if (ref.current) {
                        const rect = ref.current.getBoundingClientRect()
                        showTooltip([rect.x, rect.y, rect.width], stepIndex, step, !!funnelsQuery)
                    }
                }}
                onMouseLeave={() => hideTooltip()}
            >
                <div
                    className="StepBar__backdrop"
                    onClick={() => handleClick(false)}
                    style={{ cursor: funnelsQuery ? 'pointer' : undefined }}
                />
                <div
                    className="StepBar__fill"
                    onClick={() => handleClick(true)}
                    style={{ cursor: funnelsQuery ? 'pointer' : undefined }}
                />
            </div>
        </>
    )
}
