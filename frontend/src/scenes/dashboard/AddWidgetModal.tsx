import { useActions } from 'kea'
import { useState } from 'react'

import { LemonButton, LemonDivider, LemonModal } from '@posthog/lemon-ui'

import { DashboardWidgetType } from '~/types'

import { dashboardLogic } from './dashboardLogic'
import { isWidgetConfigValid, WidgetConfigForm, widgetTypeRequiresConfig } from './widgets/WidgetConfigForm'
import { WIDGET_TYPE_CONFIG } from './widgets/widgetTypes'

const WIDGET_TYPES = [
    DashboardWidgetType.FeatureFlag,
    DashboardWidgetType.Experiment,
    DashboardWidgetType.ErrorTracking,
    DashboardWidgetType.Logs,
    DashboardWidgetType.SessionReplays,
    DashboardWidgetType.SurveyResponses,
] as const

interface AddWidgetModalProps {
    isOpen: boolean
    onClose: () => void
}

export function AddWidgetModal({ isOpen, onClose }: AddWidgetModalProps): JSX.Element {
    const { addWidget } = useActions(dashboardLogic)
    const [step, setStep] = useState<'select' | 'configure'>('select')
    const [selectedType, setSelectedType] = useState<DashboardWidgetType | null>(null)
    const [config, setConfig] = useState<Record<string, any>>({})

    const handleClose = (): void => {
        setStep('select')
        setSelectedType(null)
        setConfig({})
        onClose()
    }

    const handleSelectType = (widgetType: DashboardWidgetType): void => {
        if (widgetTypeRequiresConfig(widgetType)) {
            // Types that need entity selection go to step 2
            setSelectedType(widgetType)
            setConfig({})
            setStep('configure')
        } else {
            // Types that don't need config are created immediately with defaults
            addWidget(widgetType, {})
            handleClose()
        }
    }

    const handleAdd = (): void => {
        if (selectedType) {
            addWidget(selectedType, config)
            handleClose()
        }
    }

    const handleBack = (): void => {
        setStep('select')
        setSelectedType(null)
        setConfig({})
    }

    const canAdd = selectedType != null && isWidgetConfigValid(selectedType, config)

    const getDisabledReason = (): string | undefined => {
        if (canAdd) {
            return undefined
        }
        switch (selectedType) {
            case DashboardWidgetType.Experiment:
                return 'Select an experiment to continue'
            case DashboardWidgetType.SurveyResponses:
                return 'Select a survey to continue'
            default:
                return 'Select a required field first'
        }
    }

    if (step === 'configure' && selectedType) {
        const typeConfig = WIDGET_TYPE_CONFIG[selectedType]
        return (
            <LemonModal isOpen={isOpen} onClose={handleClose} title={`Add ${typeConfig.label} widget`} simple>
                <LemonModal.Header>
                    <h3>Add {typeConfig.label} widget</h3>
                </LemonModal.Header>
                <LemonModal.Content>
                    <div className="flex items-center gap-3 mb-2">
                        <span
                            className="flex items-center justify-center h-8 w-8 rounded-lg shrink-0"
                            // eslint-disable-next-line react/forbid-dom-props
                            style={{
                                backgroundColor: typeConfig.color,
                                color: 'white',
                            }}
                        >
                            {typeConfig.icon}
                        </span>
                        <div className="font-medium">{typeConfig.label}</div>
                    </div>
                    <LemonDivider className="my-3" />
                    <div className="space-y-4">
                        <WidgetConfigForm widgetType={selectedType} config={config} onConfigChange={setConfig} />
                    </div>
                </LemonModal.Content>
                <LemonModal.Footer>
                    <div className="flex items-center justify-end gap-2 w-full">
                        <LemonButton type="secondary" onClick={handleBack}>
                            Back
                        </LemonButton>
                        <LemonButton type="primary" onClick={handleAdd} disabledReason={getDisabledReason()}>
                            Add to dashboard
                        </LemonButton>
                    </div>
                </LemonModal.Footer>
            </LemonModal>
        )
    }

    return (
        <LemonModal isOpen={isOpen} onClose={handleClose} title="Add widget" simple>
            <LemonModal.Header>
                <h3>Add widget</h3>
            </LemonModal.Header>
            <LemonModal.Content>
                <p className="text-muted text-sm mb-3">Embed live product data directly on your dashboard.</p>
                <div className="grid grid-cols-2 gap-2">
                    {WIDGET_TYPES.map((type, index) => {
                        const widgetConfig = WIDGET_TYPE_CONFIG[type]
                        const isLastOddItem = index === WIDGET_TYPES.length - 1 && WIDGET_TYPES.length % 2 !== 0
                        return (
                            <button
                                key={type}
                                type="button"
                                className={`flex flex-col items-start gap-2 p-3 rounded-lg border border-border text-left transition-all hover:border-primary hover:bg-primary-highlight active:scale-[0.98] cursor-pointer${isLastOddItem ? ' col-span-2' : ''}`}
                                onClick={() => handleSelectType(type)}
                            >
                                <span
                                    className="flex items-center justify-center h-8 w-8 rounded-lg shrink-0"
                                    // eslint-disable-next-line react/forbid-dom-props
                                    style={{
                                        backgroundColor: widgetConfig.color,
                                        color: 'white',
                                    }}
                                >
                                    {widgetConfig.icon}
                                </span>
                                <div>
                                    <div className="font-semibold text-sm text-text-primary">{widgetConfig.label}</div>
                                    <div className="text-xs text-muted mt-0.5">{widgetConfig.description}</div>
                                </div>
                            </button>
                        )
                    })}
                </div>
            </LemonModal.Content>
        </LemonModal>
    )
}
