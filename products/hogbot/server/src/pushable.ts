export class Pushable<T> implements AsyncIterable<T> {
    private queue: T[] = []
    private resolvers: ((value: IteratorResult<T>) => void)[] = []
    private done = false

    push(item: T): void {
        const resolve = this.resolvers.shift()
        if (resolve) {
            resolve({ value: item, done: false })
            return
        }
        this.queue.push(item)
    }

    end(): void {
        this.done = true
        for (const resolve of this.resolvers) {
            resolve({ value: undefined as T, done: true })
        }
        this.resolvers = []
    }

    [Symbol.asyncIterator](): AsyncIterator<T> {
        return {
            next: () => {
                if (this.queue.length > 0) {
                    return Promise.resolve({ value: this.queue.shift() as T, done: false })
                }
                if (this.done) {
                    return Promise.resolve({ value: undefined as T, done: true })
                }
                return new Promise<IteratorResult<T>>((resolve) => {
                    this.resolvers.push(resolve)
                })
            },
        }
    }
}
