const fs = require('fs')
const path = require('path')

function send(message) {
    if (process.send) {
        process.send(message)
    }
}

function writeResearchFile(signalId, prompt, output) {
    const workspacePath = process.env.HOGBOT_WORKSPACE_PATH
    const researchDir = path.join(workspacePath, 'research')
    fs.mkdirSync(researchDir, { recursive: true })
    const fileName = `${String(signalId).trim().replace(/[^A-Za-z0-9._-]+/g, '-') || 'research'}.md`
    fs.writeFileSync(
        path.join(researchDir, fileName),
        `# Research: ${signalId}\n\nPrompt: ${prompt}\n\n${output}\n`,
        'utf8'
    )
}

send({ type: 'ready' })

process.on('message', (message) => {
    if (!message) {
        return
    }

    if (message.type === 'shutdown') {
        process.exit(0)
        return
    }

    if (message.type !== 'start') {
        return
    }

    const finishSuccess = () => {
        const output = `research:${message.prompt}`
        writeResearchFile(message.signalId, message.prompt, output)
        send({ type: 'event', method: '_hogbot/status', params: { status: 'running', signal_id: message.signalId } })
        send({ type: 'event', method: '_hogbot/text', params: { role: 'assistant', text: output, signal_id: message.signalId } })
        send({
            type: 'event',
            method: '_hogbot/console',
            params: { level: 'info', message: `Wrote research output to research/${message.signalId}.md`, signal_id: message.signalId },
        })
        send({ type: 'event', method: '_hogbot/result', params: { output, signal_id: message.signalId } })
        send({ type: 'event', method: '_hogbot/status', params: { status: 'completed', signal_id: message.signalId } })
        send({ type: 'done', signalId: message.signalId, output })
        process.exit(0)
    }

    const finishFailure = () => {
        const error = `research failed:${message.prompt}`
        send({ type: 'event', method: '_hogbot/error', params: { message: error, signal_id: message.signalId } })
        send({ type: 'event', method: '_hogbot/status', params: { status: 'failed', message: error, signal_id: message.signalId } })
        send({ type: 'failed', signalId: message.signalId, error })
        process.exit(1)
    }

    if (message.prompt === 'slow-research') {
        setTimeout(finishSuccess, 200)
        return
    }

    if (message.prompt === 'fail-research') {
        setTimeout(finishFailure, 50)
        return
    }

    finishSuccess()
})
