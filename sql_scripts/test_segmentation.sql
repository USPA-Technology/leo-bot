-- https://chatgpt.com/share/68f373d5-e060-8000-9816-2f94e37c7ecf

-- Find top 10 similar profiles within a tenant using cosine (pgvector):
SELECT candidate.cdp_profile_id, candidate.full_name,
       candidate.profile_embedding <=> target.profile_embedding AS distance
FROM customer_profile AS target
JOIN customer_profile AS candidate
  ON candidate.tenant_id = target.tenant_id
 AND candidate.cdp_profile_id <> target.cdp_profile_id
WHERE target.tenant_id = 'default'
  AND target.cdp_profile_id = 'customer-123'
  AND candidate.profile_embedding IS NOT NULL
ORDER BY candidate.profile_embedding <=> target.profile_embedding
LIMIT 10;

-- Get churn-risk customers (experience_score <= -40):
SELECT cdp_profile_id, tenant_id, experience_score, segment_reason
FROM customer_metrics
WHERE tenant_id = 'default' AND experience_score <= -40;
