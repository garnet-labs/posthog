import './CardStackProductSelection.scss'

import clsx from 'clsx'
import { useActions } from 'kea'
import { motion, useMotionValue, useTransform, AnimatePresence } from 'motion/react'
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef } from 'react'

import { IconArrowRight, IconCheck, IconX } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { Logomark } from 'lib/brand/Logomark'
import {
    BuilderHog1,
    DetectiveHog,
    ExperimentsHog,
    ExplorerHog,
    FeatureFlagHog,
    FilmCameraHog,
    GraphsHog,
    MailHog,
    MicrophoneHog,
    RobotHog,
} from 'lib/components/hedgehogs'
import { getFeatureFlagPayload } from 'lib/logic/featureFlagLogic'

import { ProductKey } from '~/queries/schema/schema-general'

import { availableOnboardingProducts, getProductIcon, toSentenceCase } from '../utils'
import { productSelectionLogic } from './productSelectionLogic'

type AvailableOnboardingProductKey = keyof typeof availableOnboardingProducts

const PRODUCT_HEDGEHOG: Partial<Record<string, React.ComponentType<{ className?: string }>>> = {
    [ProductKey.PRODUCT_ANALYTICS]: GraphsHog,
    [ProductKey.WEB_ANALYTICS]: ExplorerHog,
    [ProductKey.SESSION_REPLAY]: FilmCameraHog,
    [ProductKey.LLM_ANALYTICS]: RobotHog,
    [ProductKey.DATA_WAREHOUSE]: BuilderHog1,
    [ProductKey.FEATURE_FLAGS]: FeatureFlagHog,
    [ProductKey.EXPERIMENTS]: ExperimentsHog,
    [ProductKey.ERROR_TRACKING]: DetectiveHog,
    [ProductKey.SURVEYS]: MicrophoneHog,
    [ProductKey.WORKFLOWS]: MailHog,
}

function getSocialProof(productKey: string): string | undefined {
    const payload = getFeatureFlagPayload('onboarding-social-proof-info') as Record<string, string> | undefined
    return (
        payload?.[productKey] ??
        availableOnboardingProducts[productKey as keyof typeof availableOnboardingProducts]?.socialProof
    )
}

// ─── Constants ──────────────────────────────────────────────────────────────
const SWIPE_THRESHOLD = 120
const SWIPE_VELOCITY_THRESHOLD = 500
const MAX_ROTATION = 18
const CARD_WIDTH = 340
const CARD_HEIGHT = 380
const FLY_OUT_X = 600

// ─── Types ──────────────────────────────────────────────────────────────────
interface SwipedCard {
    productKey: AvailableOnboardingProductKey
    pile: 'accepted' | 'rejected'
}

export interface SwipeableCardHandle {
    swipeOut: (direction: 'left' | 'right') => void
}

// ─── Pile Component ─────────────────────────────────────────────────────────
function CardPile({ cards, type }: { cards: SwipedCard[]; type: 'accepted' | 'rejected' }): JSX.Element {
    const pileCards = cards.filter((c) => c.pile === type)
    const [pulseKey, setPulseKey] = useState(0)
    const prevCountRef = useRef(pileCards.length)

    useEffect(() => {
        if (pileCards.length > prevCountRef.current) {
            setPulseKey((k) => k + 1)
        }
        prevCountRef.current = pileCards.length
    }, [pileCards.length])

    return (
        <div className="flex flex-col items-center gap-1.5">
            <div className="flex items-center gap-1 text-xs text-muted">
                {type === 'accepted' ? (
                    <IconCheck className="text-success w-3.5 h-3.5" />
                ) : (
                    <IconX className="text-muted-alt w-3.5 h-3.5" />
                )}
                <span>{pileCards.length}</span>
            </div>
            <div
                key={pulseKey}
                className={clsx(
                    'relative h-10 flex items-center',
                    pulseKey > 0 && 'CardStackProductSelection__pile-pulse'
                )}
                style={{ minWidth: Math.max(40, pileCards.length * 20 + 24) }}
            >
                {pileCards.length === 0 ? (
                    <div
                        className={clsx(
                            'w-10 h-10 rounded-lg border-2 border-dashed flex items-center justify-center',
                            type === 'accepted' ? 'border-success/30' : 'border-muted/30'
                        )}
                    >
                        {type === 'accepted' ? (
                            <IconCheck className="text-success/30 w-4 h-4" />
                        ) : (
                            <IconX className="text-muted/30 w-4 h-4" />
                        )}
                    </div>
                ) : (
                    pileCards.map((card, i) => {
                        const product = availableOnboardingProducts[card.productKey]
                        return (
                            <div
                                key={card.productKey}
                                className="absolute rounded-lg border bg-surface-primary shadow-sm flex items-center justify-center"
                                style={{
                                    width: 36,
                                    height: 40,
                                    left: i * 20,
                                    zIndex: i,
                                    borderColor: type === 'accepted' ? product.iconColor : undefined,
                                }}
                            >
                                {getProductIcon(product.icon, {
                                    iconColor: product.iconColor,
                                    className: 'text-base',
                                })}
                            </div>
                        )
                    })
                )}
            </div>
        </div>
    )
}

// ─── Swipeable Card ─────────────────────────────────────────────────────────
const SwipeableCard = forwardRef<
    SwipeableCardHandle,
    {
        productKey: AvailableOnboardingProductKey
        isTop: boolean
        stackIndex: number
        exitDirection: 'left' | 'right'
        onSwipe: (direction: 'left' | 'right') => void
    }
>(function SwipeableCard({ productKey, isTop, stackIndex, exitDirection, onSwipe }, ref) {
    const product = availableOnboardingProducts[productKey]
    const HedgehogComponent = PRODUCT_HEDGEHOG[productKey]
    const socialProof = getSocialProof(productKey)
    const description = product.userCentricDescription || product.description

    const x = useMotionValue(0)
    const rotate = useTransform(x, [-CARD_WIDTH, 0, CARD_WIDTH], [-MAX_ROTATION, 0, MAX_ROTATION])
    const acceptOpacity = useTransform(x, [0, SWIPE_THRESHOLD], [0, 1])
    const rejectOpacity = useTransform(x, [-SWIPE_THRESHOLD, 0], [1, 0])

    // Track whether we're animating out to prevent double-swipes
    const isAnimatingOut = useRef(false)

    // Expose imperative swipeOut for button/keyboard triggers
    useImperativeHandle(
        ref,
        () => ({
            swipeOut: (direction: 'left' | 'right') => {
                if (isAnimatingOut.current) {
                    return
                }
                isAnimatingOut.current = true
                onSwipe(direction)
            },
        }),
        [onSwipe]
    )

    const handleDragEnd = useCallback(
        (_: unknown, info: { offset: { x: number }; velocity: { x: number } }) => {
            if (isAnimatingOut.current) {
                return
            }
            const shouldSwipeRight = info.offset.x > SWIPE_THRESHOLD || info.velocity.x > SWIPE_VELOCITY_THRESHOLD
            const shouldSwipeLeft = info.offset.x < -SWIPE_THRESHOLD || info.velocity.x < -SWIPE_VELOCITY_THRESHOLD

            if (shouldSwipeRight) {
                isAnimatingOut.current = true
                onSwipe('right')
            } else if (shouldSwipeLeft) {
                isAnimatingOut.current = true
                onSwipe('left')
            }
        },
        [onSwipe]
    )

    // Stack depth: cards behind the top card are slightly scaled down and offset
    const stackScale = isTop ? 1 : 1 - stackIndex * 0.04
    const stackY = isTop ? 0 : stackIndex * 6
    const stackOpacity = stackIndex <= 2 ? 1 - stackIndex * 0.15 : 0

    if (stackIndex > 2) {
        return <></>
    }

    const cardVariants = {
        initial: isTop ? { scale: 1, y: 0, opacity: 1 } : { scale: stackScale, y: stackY, opacity: stackOpacity },
        animate: { scale: stackScale, y: stackY, opacity: stackOpacity },
        exit: (direction: 'left' | 'right') => ({
            x: isTop ? (direction === 'left' ? -FLY_OUT_X : FLY_OUT_X) : 0,
            opacity: 0,
            rotate: isTop ? (direction === 'left' ? -MAX_ROTATION : MAX_ROTATION) : 0,
        }),
    }

    return (
        <motion.div
            className="absolute"
            variants={cardVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            custom={exitDirection}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{
                x: isTop ? x : 0,
                rotate: isTop ? rotate : 0,
                zIndex: 10 - stackIndex,
                width: CARD_WIDTH,
                willChange: isTop ? 'transform' : 'auto',
                touchAction: 'none',
            }}
            drag={isTop ? 'x' : false}
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.9}
            onDragEnd={isTop ? handleDragEnd : undefined}
            aria-label={`${toSentenceCase(product.name)}: ${description}`}
            role="article"
        >
            <div
                className="rounded-2xl border bg-surface-primary shadow-lg overflow-hidden select-none"
                style={{
                    width: CARD_WIDTH,
                    height: CARD_HEIGHT,
                }}
            >
                {/* Color accent bar */}
                <div className="h-2" style={{ backgroundColor: product.iconColor }} />

                {/* Accept/Reject overlays */}
                {isTop && (
                    <>
                        <motion.div
                            className="absolute inset-0 rounded-2xl flex items-center justify-center pointer-events-none z-10"
                            style={{
                                opacity: acceptOpacity,
                                backgroundColor: 'rgba(34, 197, 94, 0.08)',
                            }}
                        >
                            <div className="border-4 border-success rounded-xl px-4 py-2 rotate-[-18deg]">
                                <IconCheck className="text-success w-12 h-12" />
                            </div>
                        </motion.div>
                        <motion.div
                            className="absolute inset-0 rounded-2xl flex items-center justify-center pointer-events-none z-10"
                            style={{
                                opacity: rejectOpacity,
                                backgroundColor: 'rgba(220, 38, 38, 0.06)',
                            }}
                        >
                            <div className="border-4 border-danger rounded-xl px-4 py-2 rotate-[18deg]">
                                <IconX className="text-danger w-12 h-12" />
                            </div>
                        </motion.div>
                    </>
                )}

                {/* Card content */}
                <div className="flex flex-col h-[calc(100%-8px)] p-4">
                    {/* Header: icon + product name */}
                    <div className="flex items-center gap-2 mb-3">
                        {getProductIcon(product.icon, {
                            iconColor: product.iconColor,
                            className: 'text-xl',
                        })}
                        <span className="text-xs font-medium text-muted">{toSentenceCase(product.name)}</span>
                    </div>

                    {/* Hedgehog illustration */}
                    <div
                        className="relative w-full h-20 rounded-xl mb-3 flex items-end justify-center overflow-hidden"
                        style={{ backgroundColor: `${product.iconColor}15` }}
                    >
                        {HedgehogComponent && <HedgehogComponent className="relative z-10 w-20 h-20" />}
                    </div>

                    {/* User-centric description */}
                    <h2 className="text-base font-bold mb-2 leading-snug">{description}</h2>

                    {/* Capabilities */}
                    {product.capabilities && (
                        <ul className="list-none p-0 m-0 flex flex-col gap-1 mb-2">
                            {product.capabilities.map((cap) => (
                                <li key={cap} className="text-sm text-muted flex items-center gap-2">
                                    <span
                                        className="w-1.5 h-1.5 rounded-full shrink-0"
                                        style={{ backgroundColor: product.iconColor }}
                                    />
                                    {cap}
                                </li>
                            ))}
                        </ul>
                    )}

                    {/* Social proof (pushed to bottom) */}
                    <div className="mt-auto">
                        {socialProof && <span className="text-xs text-muted">{socialProof}</span>}
                    </div>
                </div>
            </div>
        </motion.div>
    )
})

// ─── End of Deck ────────────────────────────────────────────────────────────
function EndOfDeck({
    acceptedCards,
    onContinue,
}: {
    acceptedCards: SwipedCard[]
    onContinue: () => void
}): JSX.Element {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center gap-6 text-center max-w-sm"
        >
            <h2 className="text-2xl font-bold">
                {acceptedCards.length > 0 ? "You're all set!" : 'No products selected'}
            </h2>
            {acceptedCards.length > 0 ? (
                <>
                    <p className="text-muted">
                        You picked {acceptedCards.length} product{acceptedCards.length !== 1 ? 's' : ''} to get started
                        with.
                    </p>
                    <div className="flex flex-wrap gap-2 justify-center">
                        {acceptedCards.map((card) => {
                            const product = availableOnboardingProducts[card.productKey]
                            return (
                                <div
                                    key={card.productKey}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border bg-surface-primary"
                                    style={{ borderColor: product.iconColor }}
                                >
                                    {getProductIcon(product.icon, {
                                        iconColor: product.iconColor,
                                        className: 'text-sm',
                                    })}
                                    <span className="text-sm font-medium">{toSentenceCase(product.name)}</span>
                                </div>
                            )
                        })}
                    </div>
                    <LemonButton
                        type="primary"
                        status="alt"
                        size="large"
                        onClick={onContinue}
                        sideIcon={<IconArrowRight />}
                        data-attr="onboarding-continue"
                    >
                        Get started
                    </LemonButton>
                </>
            ) : (
                <>
                    <p className="text-muted">
                        You didn't pick any products. You can always set them up later from Settings.
                    </p>
                    <LemonButton
                        type="primary"
                        status="alt"
                        size="large"
                        onClick={onContinue}
                        sideIcon={<IconArrowRight />}
                        data-attr="onboarding-continue"
                    >
                        Continue anyway
                    </LemonButton>
                </>
            )}
        </motion.div>
    )
}

// ─── Main Component ─────────────────────────────────────────────────────────
export function CardStackProductSelection(): JSX.Element {
    const { setSelectedProducts, setFirstProductOnboarding, setRecommendationSource, handleStartOnboarding } =
        useActions(productSelectionLogic)
    const allProducts = useMemo(() => Object.keys(availableOnboardingProducts) as AvailableOnboardingProductKey[], [])

    const [currentIndex, setCurrentIndex] = useState(0)
    const [swipedCards, setSwipedCards] = useState<SwipedCard[]>([])
    const [isComplete, setIsComplete] = useState(false)
    const [mounted, setMounted] = useState(false)
    // Track last exit direction so AnimatePresence exit knows which way to fly
    const [exitDirection, setExitDirection] = useState<'left' | 'right'>('right')
    const topCardRef = useRef<SwipeableCardHandle>(null)

    useEffect(() => {
        const timer = setTimeout(() => setMounted(true), 50)
        return () => clearTimeout(timer)
    }, [])

    const remainingCards = allProducts.slice(currentIndex)
    const acceptedCards = swipedCards.filter((c) => c.pile === 'accepted')

    const handleSwipe = useCallback(
        (direction: 'left' | 'right') => {
            const productKey = allProducts[currentIndex]
            setExitDirection(direction)

            const newCard: SwipedCard = {
                productKey,
                pile: direction === 'right' ? 'accepted' : 'rejected',
            }

            setSwipedCards((prev) => [...prev, newCard])

            // Track the swipe
            window.posthog?.capture('onboarding_card_swiped', {
                product: productKey,
                direction,
                card_index: currentIndex,
                total_cards: allProducts.length,
            })

            if (currentIndex + 1 >= allProducts.length) {
                setIsComplete(true)
            } else {
                setCurrentIndex((prev) => prev + 1)
            }
        },
        [allProducts, currentIndex]
    )

    const handleButtonSwipe = useCallback(
        (direction: 'left' | 'right') => {
            setExitDirection(direction)
            if (topCardRef.current) {
                topCardRef.current.swipeOut(direction)
            } else {
                handleSwipe(direction)
            }
        },
        [handleSwipe]
    )

    const handleContinue = useCallback(() => {
        const accepted = swipedCards.filter((c) => c.pile === 'accepted').map((c) => c.productKey as ProductKey)

        if (accepted.length > 0) {
            setSelectedProducts(accepted)
            setFirstProductOnboarding(accepted[0])
        } else {
            // If no products accepted, default to Product analytics
            setSelectedProducts([ProductKey.PRODUCT_ANALYTICS])
            setFirstProductOnboarding(ProductKey.PRODUCT_ANALYTICS)
        }

        setRecommendationSource('card-stack')
        handleStartOnboarding()
    }, [swipedCards, setSelectedProducts, setFirstProductOnboarding, setRecommendationSource, handleStartOnboarding])

    // Keyboard support
    useEffect(() => {
        if (isComplete) {
            return
        }

        const onKeyDown = (e: KeyboardEvent): void => {
            if (e.key === 'ArrowRight' || e.key === 'Enter') {
                e.preventDefault()
                handleButtonSwipe('right')
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault()
                handleButtonSwipe('left')
            }
        }

        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [handleButtonSwipe, isComplete])

    // Current spotlight product for background color wash
    const spotlightKey = remainingCards[0]
    const spotlightProduct = spotlightKey ? availableOnboardingProducts[spotlightKey] : null

    return (
        <div className="CardStackProductSelection flex flex-col flex-1 w-full min-h-full p-4 items-center justify-center bg-primary overflow-x-hidden">
            {/* Subtle product color wash */}
            {spotlightProduct && (
                <div
                    className="absolute inset-0 transition-colors duration-700 pointer-events-none"
                    style={{
                        backgroundColor: spotlightProduct.iconColor,
                        opacity: 0.04,
                    }}
                />
            )}

            <div className="relative flex flex-col items-center justify-center flex-grow w-full max-w-2xl">
                {/* Header */}
                <div className="flex justify-center mb-2">
                    <Logomark />
                </div>
                <h1 className="text-3xl font-bold text-center mb-1">Build your stack</h1>
                <p className="text-center text-muted mb-4">Swipe right to add a product, left to skip it.</p>

                {/* Card stack area */}
                <div
                    className="relative flex items-center justify-center mb-4"
                    style={{ width: CARD_WIDTH, height: CARD_HEIGHT + 20, isolation: 'isolate' }}
                >
                    <AnimatePresence mode="popLayout" custom={exitDirection}>
                        {!isComplete &&
                            remainingCards
                                .slice(0, 3)
                                .map((productKey, i) => (
                                    <SwipeableCard
                                        key={productKey}
                                        ref={i === 0 ? topCardRef : undefined}
                                        productKey={productKey}
                                        isTop={i === 0}
                                        stackIndex={i}
                                        exitDirection={exitDirection}
                                        onSwipe={handleSwipe}
                                    />
                                ))}
                    </AnimatePresence>

                    {isComplete && <EndOfDeck acceptedCards={acceptedCards} onContinue={handleContinue} />}
                </div>

                {/* Accept / Reject buttons + progress */}
                {!isComplete && (
                    <div
                        className={clsx(
                            'flex flex-col items-center gap-2 transition-opacity duration-300',
                            mounted ? 'opacity-100' : 'opacity-0'
                        )}
                    >
                        {/* Buttons */}
                        <div className="flex items-center gap-6">
                            <button
                                onClick={() => handleButtonSwipe('left')}
                                className="w-14 h-14 rounded-full border-2 border-danger/30 hover:border-danger hover:bg-danger/10 flex items-center justify-center transition-all cursor-pointer"
                                aria-label="Skip this product"
                            >
                                <IconX className="text-danger w-6 h-6" />
                            </button>

                            <span className="text-sm text-muted font-medium tabular-nums">
                                {currentIndex + 1} / {allProducts.length}
                            </span>

                            <button
                                onClick={() => handleButtonSwipe('right')}
                                className="w-14 h-14 rounded-full border-2 border-success/30 hover:border-success hover:bg-success/10 flex items-center justify-center transition-all cursor-pointer"
                                aria-label="Add this product"
                            >
                                <IconCheck className="text-success w-6 h-6" />
                            </button>
                        </div>

                        {/* Piles */}
                        <div className="flex items-start gap-8">
                            <CardPile cards={swipedCards} type="rejected" />
                            <CardPile cards={swipedCards} type="accepted" />
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
