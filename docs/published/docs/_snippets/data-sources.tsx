import List from 'components/List'
import { getLogo } from 'constants/logos'
import usePlatformList from 'hooks/docs/usePlatformList'
import React from 'react'

export const ManagedSources = (): React.ReactElement => {
    const platforms = usePlatformList('docs/data-warehouse/sources', 'as a source', {
        platformSourceType: 'managed',
    })

    // Add Supabase link to tutorial
    const supabase = {
        label: 'Supabase',
        url: '/tutorials/supabase-query',
        image: getLogo('supabase'),
    }

    return <List className="grid gap-4 grid-cols-2 @md:grid-cols-3 not-prose" items={[...platforms, supabase]} />
}

export const SelfHostedSources = (): React.ReactElement => {
    const platforms = usePlatformList('docs/data-warehouse/sources', 'as a source', {
        platformSourceType: 'self-hosted',
    })

    return <List className="grid gap-4 grid-cols-2 @md:grid-cols-3 not-prose" items={platforms} />
}

export const AllSources = (): React.ReactElement => {
    const platforms = usePlatformList('docs/data-warehouse/sources', 'as a source')

    // Add Supabase link to tutorial
    const supabase = {
        label: 'Supabase',
        url: '/tutorials/supabase-query',
        image: getLogo('supabase'),
    }

    return <List className="grid @2xl:grid-cols-2 @3xl:grid-cols-3 mb-4" items={[...platforms, supabase]} />
}
