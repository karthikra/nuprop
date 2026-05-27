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

# 4. Lifecycle — expire un-tagged objects after 90 days. S12 will tag
#    assets that belong to a published proposal so they survive.
echo "==> Setting lifecycle (90-day expiry on un-tagged objects)"
aws s3api put-bucket-lifecycle-configuration --bucket "${BUCKET}" --lifecycle-configuration '{
  "Rules": [
    {
      "ID": "expire-unpublished-after-90d",
      "Status": "Enabled",
      "Filter": {
        "Tag": {"Key": "published", "Value": "false"}
      },
      "Expiration": {"Days": 90}
    },
    {
      "ID": "default-expire-untagged-after-90d",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Expiration": {"Days": 90},
      "NoncurrentVersionExpiration": {"NoncurrentDays": 1}
    }
  ]
}'

echo "==> Done. Bucket ready: s3://${BUCKET}"
