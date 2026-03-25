function createSuccessResult(output) {
    return {
        type: "result",
        subtype: "success",
        result: output,
    };
}

function createErrorResult(message) {
    return {
        type: "result",
        subtype: "error_during_execution",
        errors: [message],
    };
}

function extractText(input) {
    const content = input?.message?.content;
    if (!Array.isArray(content)) {
        return "";
    }
    const firstText = content.find((item) => item?.type === "text" && typeof item.text === "string");
    return firstText?.text ?? "";
}

function createAsyncQuery(prompt) {
    const queue = [];
    const waiters = [];
    let done = false;
    let queuedError = null;
    let interruptVersion = 0;
    let releaseDelay = null;

    function resolveNext(message) {
        const waiter = waiters.shift();
        if (waiter) {
            waiter.resolve({ value: message, done: false });
            return true;
        }
        return false;
    }

    function emit(message) {
        if (!resolveNext(message)) {
            queue.push(message);
        }
    }

    function finish() {
        if (done) {
            return;
        }
        done = true;
        while (waiters.length > 0) {
            const waiter = waiters.shift();
            waiter.resolve({ value: undefined, done: true });
        }
    }

    function fail(error) {
        queuedError = error;
        while (waiters.length > 0) {
            const waiter = waiters.shift();
            waiter.reject(error);
        }
    }

    async function delay(ms) {
        const version = interruptVersion;
        await new Promise((resolve) => {
            const timer = setTimeout(() => {
                if (releaseDelay === release) {
                    releaseDelay = null;
                }
                resolve();
            }, ms);

            function release() {
                clearTimeout(timer);
                if (releaseDelay === release) {
                    releaseDelay = null;
                }
                resolve();
            }

            releaseDelay = release;
        });
        return interruptVersion !== version;
    }

    async function handleAdminInput(input) {
        const text = extractText(input);
        const interrupted = text.includes("slow") ? await delay(400) : false;
        if (done || interrupted) {
            return;
        }
        if (text.includes("fatal-admin")) {
            throw new Error("mock admin fatal");
        }
        if (text.includes("fail")) {
            emit(createErrorResult(`admin failed:${text}`));
            return;
        }
        emit(createSuccessResult(`admin:${text}`));
    }

    async function handleResearchPrompt(text) {
        const interrupted = text.includes("slow") ? await delay(250) : false;
        if (done || interrupted) {
            return;
        }
        if (text.includes("fatal-research")) {
            throw new Error("mock research fatal");
        }
        if (text.includes("fail")) {
            emit(createErrorResult(`research failed:${text}`));
            return;
        }
        emit(createSuccessResult(`research:${text}`));
    }

    Promise.resolve()
        .then(async () => {
            if (typeof prompt === "string") {
                await handleResearchPrompt(prompt);
                finish();
                return;
            }

            for await (const input of prompt) {
                if (done) {
                    break;
                }
                await handleAdminInput(input);
            }
            finish();
        })
        .catch((error) => {
            fail(error instanceof Error ? error : new Error(String(error)));
        });

    return {
        async initializationResult() {
            return { session_id: "mock-session" };
        },
        async interrupt() {
            interruptVersion += 1;
            if (releaseDelay) {
                const release = releaseDelay;
                releaseDelay = null;
                release();
            }
        },
        close() {
            if (releaseDelay) {
                const release = releaseDelay;
                releaseDelay = null;
                release();
            }
            finish();
        },
        async next() {
            if (queue.length > 0) {
                return { value: queue.shift(), done: false };
            }
            if (queuedError) {
                const error = queuedError;
                queuedError = null;
                throw error;
            }
            if (done) {
                return { value: undefined, done: true };
            }
            return await new Promise((resolve, reject) => {
                waiters.push({ resolve, reject });
            });
        },
        [Symbol.asyncIterator]() {
            return this;
        },
    };
}

function query({ prompt }) {
    return createAsyncQuery(prompt);
}

module.exports = {
    query,
};
