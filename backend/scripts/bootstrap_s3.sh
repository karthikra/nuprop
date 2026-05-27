#!/usr/bin/env bash
#
# Bootstrap the nuprop-proposal-assets bucket. Idempotent — re-running it is
# safe; existing bucket / policy / lifecycle are left alone (head check first).
#
# Usage:
#   AWS_PROFILE=nuprop bash backend/scripts/bootstrap_s3.sh
#
# Requires: awscli v2, jq.

set -euo pipefail

BUCKET="${BUCKET:-nuprop-proposal-assets}"
REGION="${AWS_REGION:-ap-northeast-1}"

echo "==> Bootstrapping s3://${BUCKET} in ${REGION}"

# 1. Create bucket if it doesn't exist.
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
    echo "    bucket already exists, skipping create"
else
    echo "    creating bucket"
    aws s3api create-bucket \
        --bucket "${BUCKET}" \
        --region "${REGION}" \
        --create-bucket-configuration "LocationConstraint=${REGION}"
fi

# 2. Block all public access (defense-in-depth; assets are presigned-URL only).
echo "==> Blocking public access"
aws s3api put-public-access-block \
    --bucket "${BUCKET}" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. CORS — allow PUT (uploads) and GET (browser <img>/<video> playback) from
#    the production + local-dev origins. Header ETag exposed for upload
#    verification.
echo "==> Setting CORS"
aws s3api put-bucket-cors --bucket "${BUCKET}" --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://nuprop.fly.dev", "http://localhost:5173"],
      "AllowedMethods": ["GET", "PUT", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}'

# 4. Lifecycle — expire un-published assets after 90 days.
#
#    S3 lifecycle rules are evaluated as a union: if ANY rule matches an
#    object, it expires. So this MUST be the only expiry rule, AND it MUST
#    be filtered on a tag the app actually sets — never a bucket-wide
#    prefix, or published assets would expire too.
#
#    S10 does not yet stamp the ``published=false`` tag on uploads. Until
#    S12 wires tag-on-upload into commit/generate, the rule matches nothing
#    and every asset stays forever. That's the safe default for the current
#    pre-published-prod state (zero real proposals). When S12 ships, the
#    existing rule catches new uploads with no further bucket changes.
echo "==> Setting lifecycle (90-day expiry on published=false-tagged objects)"
aws s3api put-bucket-lifecycle-configuration --bucket "${BUCKET}" --lifecycle-configuration '{
  "Rules": [
    {
      "ID": "expire-unpublished-after-90d",
      "Status": "Enabled",
      "Filter": {
        "Tag": {"Key": "published", "Value": "false"}
      },
      "Expiration": {"Days": 90}
    }
  ]
}'

echo "==> Done. Bucket ready: s3://${BUCKET}"
