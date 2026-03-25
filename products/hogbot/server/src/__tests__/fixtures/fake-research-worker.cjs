function send(message) {
    if (process.send) {
        process.send(message)
    }
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
        send({ type: 'event', method: '_hogbot/status', params: { status: 'running', signal_id: message.signalId } })
        send({ type: 'event', method: '_hogbot/text', params: { role: 'assistant', text: output, signal_id: message.signalId } })
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
