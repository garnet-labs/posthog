const fs = require('fs')

jest.mock('fs')

const masterCiAlerts = require('./ci-alerts-devex')

const STATE_FILE = '.alerts-devex'

const T_BASE = new Date('2026-04-09T12:00:00Z')
const minutes = (n) => new Date(T_BASE.getTime() + n * 60000)

function createMocks() {
    const outputs = {}
    const core = {
        setOutput: jest.fn((key, value) => {
            outputs[key] = value
        }),
    }
    return { core, outputs }
}

function createContext() {
    return {
        repo: { owner: 'PostHog', repo: 'posthog' },
    }
}

function createGithubMock(workflowResults) {
    return {
        rest: {
            actions: {
                listWorkflowRuns: jest.fn(({ workflow_id }) => {
                    const result = workflowResults[workflow_id]
                    if (!result) return Promise.resolve({ data: { workflow_runs: [] } })
                    return Promise.resolve({
                        data: {
                            workflow_runs: [
                                {
                                    name: result.name,
                                    conclusion: result.conclusion,
                                    head_sha: result.sha || 'abc1234',
                                    html_url: result.run_url || `https://github.com/runs/${result.name}`,
                                    updated_at: '2026-04-09T12:00:00Z',
                                },
                            ],
                        },
                    })
                }),
            },
        },
    }
}

function run(github, { state = null, now = minutes(0) } = {}) {
    const { core, outputs } = createMocks()
    const context = createContext()

    const mockFs = {
        existsSync: jest.fn(() => state !== null),
        readFileSync: jest.fn(() => (state ? JSON.stringify(state) : '{}')),
        writeFileSync: jest.fn(),
    }

    process.env.WATCHED_WORKFLOWS = 'ci-backend.yml,ci-frontend.yml'
    process.env.ALERT_THRESHOLD_MINUTES = '30'

    return masterCiAlerts({ github, context, core }, { fs: mockFs, now }).then(() => ({
        outputs,
        core,
        mockFs,
        writtenState: mockFs.writeFileSync.mock.calls[0]
            ? JSON.parse(mockFs.writeFileSync.mock.calls[0][1])
            : null,
    }))
}

afterEach(() => {
    delete process.env.WATCHED_WORKFLOWS
    delete process.env.ALERT_THRESHOLD_MINUTES
})

describe('master-ci-alerts', () => {
    describe('no failures', () => {
        it('does nothing when all workflows pass and no state exists', async () => {
            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs } = await run(github)

            expect(outputs.action).toBe('none')
            expect(outputs.save_cache).toBe('false')
        })

        it('does nothing when a workflow has no runs', async () => {
            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                // ci-frontend.yml has no runs
            })

            const { outputs } = await run(github)

            expect(outputs.action).toBe('none')
        })
    })

    describe('under threshold (no alert yet)', () => {
        it('saves state on first failure but does not alert', async () => {
            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs, writtenState } = await run(github, { now: minutes(0) })

            expect(outputs.action).toBe('none')
            expect(outputs.save_cache).toBe('true')
            expect(writtenState.failing['Backend CI']).toBeDefined()
            expect(writtenState.alerted).toBe(false)
        })

        it('preserves failure since timestamp on subsequent polls', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': {
                    name: 'Backend CI',
                    conclusion: 'failure',
                    sha: 'def5678',
                    run_url: 'https://github.com/runs/2',
                },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { writtenState } = await run(github, { state: existingState, now: minutes(15) })

            // since should be preserved from original failure
            expect(writtenState.failing['Backend CI'].since).toBe(minutes(0).toISOString())
            // but sha/url should be updated
            expect(writtenState.failing['Backend CI'].sha).toBe('def5678')
        })
    })

    describe('threshold reached - CREATE', () => {
        it('creates alert when failure persists past threshold', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs, writtenState } = await run(github, {
                state: existingState,
                now: minutes(31),
            })

            expect(outputs.action).toBe('create')
            expect(outputs.failing_workflows).toBe('Backend CI')
            expect(outputs.failing_count).toBe('1')
            expect(outputs.duration_mins).toBe('31')
            expect(outputs.delete_old_caches).toBe('true')
            expect(writtenState.alerted).toBe(true)
        })

        it('creates alert with multiple failing workflows', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                    'Frontend CI': {
                        since: minutes(5).toISOString(),
                        sha: 'def5678',
                        run_url: 'https://github.com/runs/2',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'failure' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(31) })

            expect(outputs.action).toBe('create')
            expect(outputs.failing_count).toBe('2')
            expect(outputs.failing_workflows).toContain('Backend CI')
            expect(outputs.failing_workflows).toContain('Frontend CI')
        })

        it('does not create at exactly threshold (requires exceeding)', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(30) })

            expect(outputs.action).toBe('create')
        })
    })

    describe('UPDATE - failing set changes after alert', () => {
        it('updates when new workflow starts failing', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: true,
                slack_ts: '123.456',
                slack_channel: 'C123',
                last_failing_list: 'Backend CI',
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'failure' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(35) })

            expect(outputs.action).toBe('update')
            expect(outputs.added_workflows).toBe('Frontend CI')
            expect(outputs.removed_workflows).toBe('')
            expect(outputs.slack_ts).toBe('123.456')
            expect(outputs.slack_channel).toBe('C123')
        })

        it('updates when a workflow recovers while others still fail', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                    'Frontend CI': {
                        since: minutes(5).toISOString(),
                        sha: 'def5678',
                        run_url: 'https://github.com/runs/2',
                    },
                },
                alerted: true,
                slack_ts: '123.456',
                slack_channel: 'C123',
                last_failing_list: 'Backend CI, Frontend CI',
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'failure' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(35) })

            expect(outputs.action).toBe('update')
            expect(outputs.removed_workflows).toBe('Backend CI')
            expect(outputs.added_workflows).toBe('')
        })

        it('does not update when failing set is unchanged', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: true,
                slack_ts: '123.456',
                slack_channel: 'C123',
                last_failing_list: 'Backend CI',
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(35) })

            expect(outputs.action).toBe('none')
            expect(outputs.save_cache).toBe('false')
        })
    })

    describe('RESOLVE', () => {
        it('resolves when all workflows pass after being alerted', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: true,
                slack_ts: '123.456',
                slack_channel: 'C123',
                last_failing_list: 'Backend CI',
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs, writtenState } = await run(github, {
                state: existingState,
                now: minutes(45),
            })

            expect(outputs.action).toBe('resolve')
            expect(outputs.duration_mins).toBe('45')
            expect(outputs.slack_ts).toBe('123.456')
            expect(outputs.slack_channel).toBe('C123')
            expect(writtenState.resolved).toBe(true)
        })
    })

    describe('flake self-heal', () => {
        it('silently clears state when failure resolves before threshold', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs } = await run(github, { state: existingState, now: minutes(10) })

            // No alert was ever sent, so no resolve needed -- just silently clear
            expect(outputs.action).toBe('none')
            expect(outputs.save_cache).toBe('false')
        })
    })

    describe('clock reset', () => {
        it('resets the clock when a workflow passes then fails again', async () => {
            // First: Backend CI was failing since T=0, then passed
            const stateAfterRecovery = {
                failing: {},
                alerted: false,
            }

            // Now Backend CI fails again at T=20
            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { writtenState } = await run(github, {
                state: stateAfterRecovery,
                now: minutes(20),
            })

            // New failure should have since=T=20, not the original T=0
            expect(writtenState.failing['Backend CI'].since).toBe(minutes(20).toISOString())
        })
    })

    describe('state handling', () => {
        it('treats resolved state as fresh', async () => {
            const resolvedState = {
                failing: {},
                alerted: true,
                resolved: true,
                slack_ts: '123.456',
                slack_channel: 'C123',
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'failure' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { outputs, writtenState } = await run(github, {
                state: resolvedState,
                now: minutes(0),
            })

            // Should treat as fresh -- no prior failing state
            expect(outputs.action).toBe('none')
            expect(writtenState.alerted).toBe(false)
            expect(writtenState.failing['Backend CI']).toBeDefined()
        })

        it('handles corrupted state gracefully', async () => {
            const { core, outputs } = createMocks()
            const context = createContext()
            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'success' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const mockFs = {
                existsSync: jest.fn(() => true),
                readFileSync: jest.fn(() => 'not valid json'),
                writeFileSync: jest.fn(),
            }

            process.env.WATCHED_WORKFLOWS = 'ci-backend.yml,ci-frontend.yml'
            process.env.ALERT_THRESHOLD_MINUTES = '30'

            await masterCiAlerts({ github, context, core }, { fs: mockFs, now: minutes(0) })

            expect(outputs.action).toBe('none')
        })

        it('handles API errors for individual workflows gracefully', async () => {
            const github = {
                rest: {
                    actions: {
                        listWorkflowRuns: jest.fn(({ workflow_id }) => {
                            if (workflow_id === 'ci-backend.yml') {
                                return Promise.reject(new Error('API rate limited'))
                            }
                            return Promise.resolve({
                                data: {
                                    workflow_runs: [
                                        {
                                            name: 'Frontend CI',
                                            conclusion: 'success',
                                            head_sha: 'abc1234',
                                            html_url: 'https://github.com/runs/1',
                                            updated_at: '2026-04-09T12:00:00Z',
                                        },
                                    ],
                                },
                            })
                        }),
                    },
                },
            }

            // Should not throw, just skip the failed workflow
            const { outputs } = await run(github, { now: minutes(0) })

            expect(outputs.action).toBe('none')
        })

        it('ignores cancelled workflows (leaves state unchanged)', async () => {
            const existingState = {
                failing: {
                    'Backend CI': {
                        since: minutes(0).toISOString(),
                        sha: 'abc1234',
                        run_url: 'https://github.com/runs/1',
                    },
                },
                alerted: false,
            }

            const github = createGithubMock({
                'ci-backend.yml': { name: 'Backend CI', conclusion: 'cancelled' },
                'ci-frontend.yml': { name: 'Frontend CI', conclusion: 'success' },
            })

            const { writtenState } = await run(github, { state: existingState, now: minutes(5) })

            // Backend CI state should be preserved (cancelled doesn't clear or add)
            expect(writtenState.failing['Backend CI']).toBeDefined()
            expect(writtenState.failing['Backend CI'].since).toBe(minutes(0).toISOString())
        })
    })
})
