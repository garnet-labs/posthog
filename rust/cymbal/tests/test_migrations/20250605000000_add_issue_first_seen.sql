-- Add first_seen column to posthog_errortrackingissue
ALTER TABLE posthog_errortrackingissue ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ;
