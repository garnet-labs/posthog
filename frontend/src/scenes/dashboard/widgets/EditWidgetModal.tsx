import { useEffect, useState } from 'react'

import { LemonButton, LemonModal } from '@posthog/lemon-ui'

import { DashboardWidgetModel } from '~/types'

import { isWidgetConfigValid, WidgetConfigForm } from './WidgetConfigForm'
import { WIDGET_TYPE_CONFIG } from './widgetTypes'

interface EditWidgetModalProps {
    isOpen: boolean
    onClose: () => void
    widget: DashboardWidgetModel
    onSave: (config: Record<string, any>) => void
}

export function EditWidgetModal({ isOpen, onClose, widget, onSave }: EditWidgetModalProps): JSX.Element {
    const [config, setConfig] = useState<Record<string, any>>(widget.config || {})

    useEffect(() => {
        if (isOpen) {
            setConfig(widget.config || {})
        }
    }, [isOpen, widget.config])

    const handleSave = (): void => {
        onSave(config)
        onClose()
    }

    const typeConfig = WIDGET_TYPE_CONFIG[widget.widget_type]
    const canSave = isWidgetConfigValid(widget.widget_type, config)

    return (
        <LemonModal
            isOpen={isOpen}
            onClose={onClose}
            title={`Edit ${typeConfig.label} widget`}
            footer={
                <>
                    <LemonButton type="secondary" onClick={onClose}>
                        Cancel
                    </LemonButton>
                    <LemonButton
                        type="primary"
                        onClick={handleSave}
                        disabledReason={!canSave ? 'Please fill in all required fields' : undefined}
                    >
                        Save
                    </LemonButton>
                </>
            }
        >
            <div className="space-y-4">
                <WidgetConfigForm widgetType={widget.widget_type} config={config} onConfigChange={setConfig} />
            </div>
        </LemonModal>
    )
}
