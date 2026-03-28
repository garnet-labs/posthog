import { useActions, useValues } from 'kea'

import { IconPlus, IconTrash } from '@posthog/icons'
import { LemonButton, LemonSegmentedButton } from '@posthog/lemon-ui'

import { LemonInput } from 'lib/lemon-ui/LemonInput'
import { LemonRadio } from 'lib/lemon-ui/LemonRadio'
import { LemonSelect } from 'lib/lemon-ui/LemonSelect'
import { LemonTextArea } from 'lib/lemon-ui/LemonTextArea'

import { ToolbarMenu } from '~/toolbar/bar/ToolbarMenu'

import {
    FREQUENCY_OPTIONS,
    type QuickSurveyQuestionType,
    type WizardStep,
    surveysToolbarLogic,
} from '../surveysToolbarLogic'

const QUESTION_TYPE_OPTIONS = [
    { value: 'open' as const, label: 'Open text' },
    { value: 'rating' as const, label: 'Rating scale' },
    { value: 'single_choice' as const, label: 'Single choice' },
]

const STEP_LABELS: Record<WizardStep, string> = {
    question: 'Question',
    where: 'Where',
    when: 'When',
}

function StepIndicator({ currentStep }: { currentStep: WizardStep }): JSX.Element {
    const steps: WizardStep[] = ['question', 'where', 'when']
    const currentIndex = steps.indexOf(currentStep)

    return (
        <div className="flex items-center gap-1 justify-center">
            {steps.map((step, i) => (
                <div key={step} className="flex items-center gap-1">
                    <div
                        className={`flex items-center justify-center w-5 h-5 rounded-full text-xs font-medium ${
                            i <= currentIndex ? 'bg-primary text-primary-foreground' : 'bg-fill-secondary text-muted'
                        }`}
                    >
                        {i + 1}
                    </div>
                    <span className={`text-xs ${i === currentIndex ? 'font-medium' : 'text-muted'}`}>
                        {STEP_LABELS[step]}
                    </span>
                    {i < steps.length - 1 && <span className="text-muted mx-0.5">—</span>}
                </div>
            ))}
        </div>
    )
}

function QuestionStep(): JSX.Element {
    const { quickForm } = useValues(surveysToolbarLogic)
    const { setFormField } = useActions(surveysToolbarLogic)

    return (
        <div className="space-y-3">
            <div>
                <label className="text-xs font-medium text-muted mb-0.5 block">Name</label>
                <LemonInput
                    autoFocus
                    placeholder="e.g. Feedback on checkout"
                    fullWidth
                    size="small"
                    value={quickForm.name}
                    onChange={(v) => setFormField('name', v)}
                />
            </div>

            <div>
                <label className="text-xs font-medium text-muted mb-0.5 block">Question type</label>
                <LemonSelect
                    fullWidth
                    size="small"
                    options={QUESTION_TYPE_OPTIONS}
                    value={quickForm.questionType}
                    onChange={(v) => setFormField('questionType', v as QuickSurveyQuestionType)}
                />
            </div>

            <div>
                <label className="text-xs font-medium text-muted mb-0.5 block">Question</label>
                <LemonTextArea
                    placeholder="What would you like to ask?"
                    value={quickForm.questionText}
                    onChange={(v) => setFormField('questionText', v)}
                    minRows={2}
                    maxRows={4}
                />
            </div>

            {quickForm.questionType === 'rating' && (
                <>
                    <div>
                        <label className="text-xs font-medium text-muted mb-0.5 block">Scale</label>
                        <LemonSelect
                            fullWidth
                            size="small"
                            options={[
                                { value: 5, label: '1–5' },
                                { value: 10, label: '1–10 (NPS)' },
                            ]}
                            value={quickForm.ratingScale}
                            onChange={(v) => setFormField('ratingScale', v)}
                        />
                    </div>
                    <div className="flex gap-2">
                        <div className="flex-1">
                            <label className="text-xs font-medium text-muted mb-0.5 block">Low label</label>
                            <LemonInput
                                size="small"
                                fullWidth
                                value={quickForm.ratingLowerLabel}
                                onChange={(v) => setFormField('ratingLowerLabel', v)}
                            />
                        </div>
                        <div className="flex-1">
                            <label className="text-xs font-medium text-muted mb-0.5 block">High label</label>
                            <LemonInput
                                size="small"
                                fullWidth
                                value={quickForm.ratingUpperLabel}
                                onChange={(v) => setFormField('ratingUpperLabel', v)}
                            />
                        </div>
                    </div>
                </>
            )}

            {quickForm.questionType === 'single_choice' && (
                <div>
                    <label className="text-xs font-medium text-muted mb-0.5 block">Choices</label>
                    <div className="space-y-1">
                        {quickForm.choices.map((choice, i) => (
                            <div key={i} className="flex gap-1 items-center">
                                <LemonInput
                                    size="small"
                                    fullWidth
                                    placeholder={`Option ${i + 1}`}
                                    value={choice}
                                    onChange={(v) => {
                                        const newChoices = [...quickForm.choices]
                                        newChoices[i] = v
                                        setFormField('choices', newChoices)
                                    }}
                                />
                                {quickForm.choices.length > 2 && (
                                    <LemonButton
                                        size="xsmall"
                                        icon={<IconTrash />}
                                        onClick={() => {
                                            const newChoices = quickForm.choices.filter((_, j) => j !== i)
                                            setFormField('choices', newChoices)
                                        }}
                                    />
                                )}
                            </div>
                        ))}
                        {quickForm.choices.length < 6 && (
                            <LemonButton
                                size="xsmall"
                                type="secondary"
                                icon={<IconPlus />}
                                fullWidth
                                onClick={() => setFormField('choices', [...quickForm.choices, ''])}
                            >
                                Add option
                            </LemonButton>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

function WhereStep(): JSX.Element {
    const { quickForm } = useValues(surveysToolbarLogic)
    const { setFormField } = useActions(surveysToolbarLogic)

    return (
        <div className="space-y-4">
            <div>
                <h3 className="text-sm font-semibold mb-1">Where should this appear?</h3>
                <p className="text-xs text-muted mb-3">Choose which pages will show this survey</p>

                <LemonRadio
                    value={quickForm.targetingMode}
                    onChange={(v) => setFormField('targetingMode', v)}
                    options={[
                        {
                            value: 'all',
                            label: 'All pages',
                            description: 'Survey can appear anywhere on your site',
                        },
                        {
                            value: 'specific',
                            label: 'Specific pages',
                            description: 'Only show on pages matching a URL pattern',
                        },
                    ]}
                />

                {quickForm.targetingMode === 'specific' && (
                    <div className="mt-3 ml-6">
                        <LemonInput
                            size="small"
                            fullWidth
                            placeholder="/pricing"
                            value={quickForm.urlMatch}
                            onChange={(v) => setFormField('urlMatch', v)}
                        />
                        <span className="text-xs text-muted mt-0.5 block">
                            Auto-filled from current page. Uses &quot;contains&quot; matching.
                        </span>
                    </div>
                )}
            </div>

            <div className="border-t border-border pt-4">
                <h3 className="text-sm font-semibold mb-1">How often can someone see this?</h3>
                <p className="text-xs text-muted mb-3">Control how frequently the same person sees this survey</p>

                <LemonSegmentedButton
                    value={quickForm.frequency}
                    onChange={(v) => setFormField('frequency', v)}
                    options={FREQUENCY_OPTIONS.map((opt) => ({
                        value: opt.value,
                        label: opt.label,
                    }))}
                    fullWidth
                    size="small"
                />
            </div>
        </div>
    )
}

function WhenStep(): JSX.Element {
    const { quickForm } = useValues(surveysToolbarLogic)
    const { setFormField } = useActions(surveysToolbarLogic)

    return (
        <div className="space-y-4">
            <div>
                <h3 className="text-sm font-semibold mb-1">When should this appear?</h3>
                <p className="text-xs text-muted mb-3">Choose when to show this survey to your users</p>

                <LemonRadio
                    value={quickForm.triggerMode}
                    onChange={(v) => setFormField('triggerMode', v)}
                    options={[
                        {
                            value: 'pageview',
                            label: 'On page load',
                            description: 'Shows when the user visits the page',
                        },
                        {
                            value: 'event',
                            label: 'When an event is captured',
                            description: 'Trigger the survey after a specific event',
                        },
                    ]}
                />

                {quickForm.triggerMode === 'event' && (
                    <div className="mt-3 ml-6">
                        <LemonInput
                            size="small"
                            fullWidth
                            placeholder="e.g. purchase_completed"
                            value={quickForm.triggerEventName}
                            onChange={(v) => setFormField('triggerEventName', v)}
                        />
                        <span className="text-xs text-muted mt-0.5 block">
                            Enter the event name that triggers this survey
                        </span>
                    </div>
                )}
            </div>

            <div className="border-t border-border pt-4">
                <h3 className="text-sm font-semibold mb-1">Delay before showing</h3>
                <div className="flex items-center gap-2">
                    <LemonInput
                        type="number"
                        min={0}
                        size="small"
                        value={quickForm.delaySeconds}
                        onChange={(val) => setFormField('delaySeconds', Number(val) || 0)}
                        className="w-20"
                    />
                    <span className="text-xs text-muted">seconds after conditions are met</span>
                </div>
            </div>
        </div>
    )
}

export function SurveyQuickCreate(): JSX.Element {
    const { wizardStep, isSubmitting, canProceed, isLastStep } = useValues(surveysToolbarLogic)
    const { nextStep, prevStep, cancelQuickCreate, submitQuickCreate } = useActions(surveysToolbarLogic)

    return (
        <ToolbarMenu>
            <ToolbarMenu.Header>
                <StepIndicator currentStep={wizardStep} />
            </ToolbarMenu.Header>
            <ToolbarMenu.Body>
                <div className="py-1">
                    {wizardStep === 'question' && <QuestionStep />}
                    {wizardStep === 'where' && <WhereStep />}
                    {wizardStep === 'when' && <WhenStep />}
                </div>
            </ToolbarMenu.Body>
            <ToolbarMenu.Footer>
                <LemonButton
                    size="small"
                    type="secondary"
                    onClick={wizardStep === 'question' ? cancelQuickCreate : prevStep}
                    className="shrink-0"
                >
                    {wizardStep === 'question' ? 'Cancel' : 'Back'}
                </LemonButton>
                <div className="flex-1">
                    {isLastStep ? (
                        <LemonButton
                            size="small"
                            type="primary"
                            fullWidth
                            center
                            loading={isSubmitting}
                            disabledReason={!canProceed ? 'Fill in the required fields' : undefined}
                            onClick={submitQuickCreate}
                        >
                            Create draft
                        </LemonButton>
                    ) : (
                        <LemonButton
                            size="small"
                            type="primary"
                            fullWidth
                            center
                            disabledReason={!canProceed ? 'Fill in the name and question' : undefined}
                            onClick={nextStep}
                        >
                            Next
                        </LemonButton>
                    )}
                </div>
            </ToolbarMenu.Footer>
        </ToolbarMenu>
    )
}
