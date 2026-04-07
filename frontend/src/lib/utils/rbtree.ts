// TypeScript port of https://github.com/vadimg/js_bintrees (MIT License)
// Original copyright 2013 Vadim Graboys

class RBNode<T> {
    data: T
    left: RBNode<T> | null = null
    right: RBNode<T> | null = null
    red: boolean = true

    constructor(data: T) {
        this.data = data
    }

    getChild(dir: boolean): RBNode<T> | null {
        return dir ? this.right : this.left
    }

    setChild(dir: boolean, val: RBNode<T> | null): void {
        if (dir) {
            this.right = val
        } else {
            this.left = val
        }
    }
}

export class RBTreeIterator<T> {
    private _tree: RBTree<T>
    _ancestors: RBNode<T>[]
    _cursor: RBNode<T> | null

    constructor(tree: RBTree<T>) {
        this._tree = tree
        this._ancestors = []
        this._cursor = null
    }

    data(): T | null {
        return this._cursor !== null ? this._cursor.data : null
    }

    // If null-iterator, returns first node; otherwise returns next node.
    next(): T | null {
        if (this._cursor === null) {
            const root = this._tree._root
            if (root !== null) {
                this._minNode(root)
            }
        } else {
            if (this._cursor.right === null) {
                let save: RBNode<T>
                do {
                    save = this._cursor
                    if (this._ancestors.length) {
                        this._cursor = this._ancestors.pop()!
                    } else {
                        this._cursor = null
                        break
                    }
                } while (this._cursor.right === save)
            } else {
                this._ancestors.push(this._cursor)
                this._minNode(this._cursor.right)
            }
        }
        return this._cursor !== null ? this._cursor.data : null
    }

    // If null-iterator, returns last node; otherwise returns previous node.
    prev(): T | null {
        if (this._cursor === null) {
            const root = this._tree._root
            if (root !== null) {
                this._maxNode(root)
            }
        } else {
            if (this._cursor.left === null) {
                let save: RBNode<T>
                do {
                    save = this._cursor
                    if (this._ancestors.length) {
                        this._cursor = this._ancestors.pop()!
                    } else {
                        this._cursor = null
                        break
                    }
                } while (this._cursor.left === save)
            } else {
                this._ancestors.push(this._cursor)
                this._maxNode(this._cursor.left)
            }
        }
        return this._cursor !== null ? this._cursor.data : null
    }

    private _minNode(start: RBNode<T>): void {
        while (start.left !== null) {
            this._ancestors.push(start)
            start = start.left
        }
        this._cursor = start
    }

    private _maxNode(start: RBNode<T>): void {
        while (start.right !== null) {
            this._ancestors.push(start)
            start = start.right
        }
        this._cursor = start
    }
}

export class RBTree<T> {
    _root: RBNode<T> | null = null
    size: number = 0
    private _comparator: (a: T, b: T) => number

    constructor(comparator: (a: T, b: T) => number) {
        this._comparator = comparator
    }

    clear(): void {
        this._root = null
        this.size = 0
    }

    find(data: T): T | null {
        let res = this._root
        while (res !== null) {
            const c = this._comparator(data, res.data)
            if (c === 0) {
                return res.data
            }
            res = res.getChild(c > 0)
        }
        return null
    }

    findIter(data: T): RBTreeIterator<T> {
        let res = this._root
        const iter = this.iterator()
        while (res !== null) {
            const c = this._comparator(data, res.data)
            if (c === 0) {
                iter._cursor = res
                return iter
            }
            iter._ancestors.push(res)
            res = res.getChild(c > 0)
        }
        return iter
    }

    // Returns an iterator to the node at or immediately after item.
    lowerBound(item: T): RBTreeIterator<T> {
        let cur = this._root
        const iter = this.iterator()
        const cmp = this._comparator

        while (cur !== null) {
            const c = cmp(item, cur.data)
            if (c === 0) {
                iter._cursor = cur
                return iter
            }
            iter._ancestors.push(cur)
            cur = cur.getChild(c > 0)
        }

        for (let i = iter._ancestors.length - 1; i >= 0; --i) {
            cur = iter._ancestors[i]
            if (cmp(item, cur.data) < 0) {
                iter._cursor = cur
                iter._ancestors.length = i
                return iter
            }
        }

        iter._ancestors.length = 0
        return iter
    }

    // Returns an iterator to the node immediately after item.
    upperBound(item: T): RBTreeIterator<T> {
        const iter = this.lowerBound(item)
        const cmp = this._comparator
        while (iter.data() !== null && cmp(iter.data()!, item) === 0) {
            iter.next()
        }
        return iter
    }

    min(): T | null {
        let res = this._root
        if (res === null) {
            return null
        }
        while (res.left !== null) {
            res = res.left
        }
        return res.data
    }

    max(): T | null {
        let res = this._root
        if (res === null) {
            return null
        }
        while (res.right !== null) {
            res = res.right
        }
        return res.data
    }

    iterator(): RBTreeIterator<T> {
        return new RBTreeIterator(this)
    }

    each(cb: (data: T) => void): void {
        const it = this.iterator()
        let data: T | null
        while ((data = it.next()) !== null) {
            cb(data)
        }
    }

    reach(cb: (data: T) => void): void {
        const it = this.iterator()
        let data: T | null
        while ((data = it.prev()) !== null) {
            cb(data)
        }
    }

    // Returns true if inserted, false if duplicate.
    insert(data: T): boolean {
        if (this._root === null) {
            this._root = new RBNode(data)
            this._root.red = false
            this.size++
            return true
        }

        const head = new RBNode<T>(data) // fake root, data unused

        let dir = false
        let last = false

        let gp: RBNode<T> | null = null
        let ggp: RBNode<T> = head
        let p: RBNode<T> | null = null
        let node: RBNode<T> | null = this._root
        ggp.right = this._root

        let ret = false

        while (true) {
            if (node === null) {
                node = new RBNode(data)
                p!.setChild(dir, node)
                ret = true
                this.size++
            } else if (isRed(node.left) && isRed(node.right)) {
                node.red = true
                node.left!.red = false
                node.right!.red = false
            }

            if (isRed(node) && isRed(p)) {
                const dir2 = ggp.right === gp
                if (node === p!.getChild(last)) {
                    ggp.setChild(dir2, singleRotate(gp!, !last))
                } else {
                    ggp.setChild(dir2, doubleRotate(gp!, !last))
                }
            }

            const cmp = this._comparator(node.data, data)
            if (cmp === 0) {
                break
            }

            last = dir
            dir = cmp < 0

            if (gp !== null) {
                ggp = gp
            }
            gp = p
            p = node
            node = node.getChild(dir)
        }

        this._root = head.right
        this._root!.red = false

        return ret
    }

    // Returns true if removed, false if not found.
    remove(data: T): boolean {
        if (this._root === null) {
            return false
        }

        const head = new RBNode<T>(data) // fake root, data unused
        let node: RBNode<T> = head
        node.right = this._root
        let p: RBNode<T> | null = null
        let gp: RBNode<T> | null = null
        let found: RBNode<T> | null = null
        let dir = true

        while (node.getChild(dir) !== null) {
            const last = dir

            gp = p
            p = node
            node = node.getChild(dir)!

            const cmp = this._comparator(data, node.data)
            dir = cmp > 0

            if (cmp === 0) {
                found = node
            }

            if (!isRed(node) && !isRed(node.getChild(dir))) {
                if (isRed(node.getChild(!dir))) {
                    const sr = singleRotate(node, dir)
                    p.setChild(last, sr)
                    p = sr
                } else if (!isRed(node.getChild(!dir))) {
                    const sibling = p.getChild(!last)
                    if (sibling !== null) {
                        if (!isRed(sibling.getChild(!last)) && !isRed(sibling.getChild(last))) {
                            p.red = false
                            sibling.red = true
                            node.red = true
                        } else {
                            const dir2 = gp!.right === p
                            if (isRed(sibling.getChild(last))) {
                                gp!.setChild(dir2, doubleRotate(p, last))
                            } else if (isRed(sibling.getChild(!last))) {
                                gp!.setChild(dir2, singleRotate(p, last))
                            }
                            const gpc = gp!.getChild(dir2)!
                            gpc.red = true
                            node.red = true
                            gpc.left!.red = false
                            gpc.right!.red = false
                        }
                    }
                }
            }
        }

        if (found !== null) {
            found.data = node.data
            p!.setChild(p!.right === node, node.getChild(node.left === null))
            this.size--
        }

        this._root = head.right
        if (this._root !== null) {
            this._root.red = false
        }

        return found !== null
    }
}

function isRed<T>(node: RBNode<T> | null): boolean {
    return node !== null && node.red
}

function singleRotate<T>(root: RBNode<T>, dir: boolean): RBNode<T> {
    const save = root.getChild(!dir)!
    root.setChild(!dir, save.getChild(dir))
    save.setChild(dir, root)
    root.red = true
    save.red = false
    return save
}

function doubleRotate<T>(root: RBNode<T>, dir: boolean): RBNode<T> {
    root.setChild(!dir, singleRotate(root.getChild(!dir)!, !dir))
    return singleRotate(root, dir)
}
