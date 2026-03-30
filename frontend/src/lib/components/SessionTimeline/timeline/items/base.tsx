export function BasePreview({
    name,
    description,
    descriptionTitle,
}: {
    name: React.ReactNode
    descriptionTitle?: string
    description?: React.ReactNode
}): JSX.Element {
    return (
        <div className="flex justify-between items-center">
            <span className="font-medium">{name}</span>
            {description && (
                <span className="text-secondary text-xs line-clamp-1 max-w-2/3 text-right" title={descriptionTitle}>
                    {description}
                </span>
            )}
        </div>
    )
}
