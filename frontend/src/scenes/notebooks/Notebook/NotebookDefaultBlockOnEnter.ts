import { Extension } from '@tiptap/core'

/**
 * On Enter, new blocks start as plain body text (paragraph + no carried marks).
 * Mirrors the default TipTap keymap chain but uses splitBlock({ keepMarks: false })
 * so bold/italic/code and similar marks are not inherited onto the new line.
 */
export const NotebookDefaultBlockOnEnter = Extension.create({
    name: 'notebookDefaultBlockOnEnter',

    // Run before the built-in keymap extension (priority 100) so Enter is handled here first.
    priority: 200,

    addKeyboardShortcuts() {
        const handleEnter = (): boolean =>
            this.editor.commands.first(({ commands }) => [
                () => commands.newlineInCode(),
                () => commands.createParagraphNear(),
                () => commands.liftEmptyBlock(),
                () => commands.splitBlock({ keepMarks: false }),
            ])

        return {
            Enter: handleEnter,
        }
    },
})
