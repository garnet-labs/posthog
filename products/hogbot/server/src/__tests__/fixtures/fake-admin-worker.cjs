let pending = null

function send(message) {
    if (process.send) {
        process.send(message)
    }
}

send({ type: 'ready', sessionId: 'fake-admin-session' })

process.on('message', (message) => {
    if (!message) {
        return
    }

    if (message.type === 'shutdown') {
        process.exit(0)
        return
    }

    if (message.type === 'cancel') {
        if (pending) {
            clearTimeout(pending.timer)
            pending = null
        }
        send({ type: 'event', method: '_hogbot/status', params: { status: 'cancelled' } })
        send({ type: 'cancelled', requestId: message.requestId })
        return
    }

    if (message.type !== 'send_message') {
        return
    }

    if (message.content === 'crash-now') {
        process.exit(1)
        return
    }

    if (message.content === 'request-error') {
        send({ type: 'request_error', requestId: message.requestId, error: 'Synthetic admin failure' })
        return
    }

    const respond = () => {
        const response = `admin:${message.content}`
        send({ type: 'event', method: '_hogbot/status', params: { status: 'running' } })
        send({ type: 'event', method: '_hogbot/text', params: { role: 'assistant', text: response } })
        send({ type: 'event', method: '_hogbot/result', params: { output: response } })
        send({ type: 'event', method: '_hogbot/status', params: { status: 'completed' } })
        send({ type: 'response', requestId: message.requestId, response })
        pending = null
    }

    if (message.content === 'slow-admin') {
        pending = { timer: setTimeout(respond, 200) }
        send({ type: 'event', method: '_hogbot/status', params: { status: 'running' } })
        return
    }

    respond()
})
