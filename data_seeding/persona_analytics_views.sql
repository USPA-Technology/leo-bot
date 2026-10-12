-- ============================================================================
-- PERSONA ANALYTICS | VIEW CHO DASHBOARD BÁO CÁO
-- Chạy SAU khi đã cài schema đầy đủ (persona_*, recommendation_*, customer_profile).
--
-- Nguyên tắc
--  * Mọi view dùng security_invoker = true, nên RLS của người gọi vẫn được áp dụng.
--  * Mọi view có cột tenant_id. Dashboard luôn lọc theo tenant.
--  * Không sửa dữ liệu. Chỉ đọc.
--  * Ngưỡng dùng chung nằm trong hàm persona_gap_band() để đổi một chỗ là đủ.
--
-- Bản đồ dashboard
--  Thẻ KPI ............ v_persona_kpi_overview
--  Xu hướng nhóm ...... v_persona_cohort_trend
--  Heatmap chiều ...... v_persona_dimension_gap
--  Bảng mục tiêu ...... v_persona_goal_status
--  Hiệu quả gợi ý ..... v_reco_item_performance
--  Lý do bị loại ...... v_reco_exclusion_reasons
--  Gợi ý theo ngày .... v_reco_daily
--  Consent ............ v_persona_consent_health
--  Chất lượng bằng chứng  v_persona_evidence_quality
--  Panel chất lượng dữ liệu v_persona_dq_checks
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 0. HÀM TIỆN ÍCH
-- ----------------------------------------------------------------------------

-- Nhóm thế hệ từ năm sinh (dùng cho phân tích theo cohort)
CREATE OR REPLACE FUNCTION persona_cohort(p_birth DATE) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_birth IS NULL THEN 'Chưa rõ'
        WHEN EXTRACT(YEAR FROM p_birth) BETWEEN 1970 AND 1982 THEN '1970–1982'
        WHEN EXTRACT(YEAR FROM p_birth) BETWEEN 1983 AND 1995 THEN '1983–1995'
        WHEN EXTRACT(YEAR FROM p_birth) BETWEEN 1996 AND 2008 THEN '1996–2008'
        ELSE 'Ngoài khoảng'
    END;
$$;

-- Dải khoảng cách: TG càng thấp càng gần mục tiêu
-- Ngưỡng: <= 0.05 đạt mục tiêu; <= 0.15 gần đạt; còn lại đang tiến triển
CREATE OR REPLACE FUNCTION persona_gap_band(p_tg REAL) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_tg IS NULL THEN 'Chưa đo'
        WHEN p_tg <= 0.05 THEN 'Đạt mục tiêu'
        WHEN p_tg <= 0.15 THEN 'Gần đạt'
        ELSE 'Đang tiến triển'
    END;
$$;


-- ----------------------------------------------------------------------------
-- 1. NHÓM NGƯỜI DÙNG
-- Khớp với persona qua cdp_profile_id (không dùng user_id để nối).
-- Ngày sinh đọc từ metadata: 'birth_date' hoặc 'ngay_sinh'.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_user_cohort WITH (security_invoker = true) AS
SELECT
    cp.tenant_id,
    cp.cdp_profile_id,
    cp.full_name,
    cp.age,
    CASE
        WHEN COALESCE(cp.metadata->>'birth_date', cp.metadata->>'ngay_sinh') IS NULL THEN 'Chưa rõ'
        ELSE persona_cohort(COALESCE(cp.metadata->>'birth_date', cp.metadata->>'ngay_sinh')::date)
    END AS cohort
FROM customer_profile cp;


-- ----------------------------------------------------------------------------
-- 2. QUỸ ĐẠO: mỗi state (không tính bản tái phân tích) kèm bước thứ mấy của người đó
-- Dùng cho xu hướng "nhàm chán -> vui hơn" theo thời gian.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_trajectory WITH (security_invoker = true) AS
SELECT
    s.tenant_id,
    s.user_id,
    s.cdp_profile_id,
    COALESCE(c.cohort, 'Chưa rõ') AS cohort,
    s.id AS state_id,
    s.goal_id,
    s.as_of::date AS state_date,
    ROW_NUMBER() OVER (PARTITION BY s.tenant_id, s.user_id ORDER BY s.as_of) AS step_no,
    g.tg,
    g.pas,
    g.tv,
    g.pd,
    g.dims_in_scope,
    persona_gap_band(g.tg) AS band
FROM persona_states s
JOIN persona_gap_snapshots g
  ON g.tenant_id = s.tenant_id AND g.state_id = s.id AND NOT g.is_reanalysis
LEFT JOIN v_persona_user_cohort c
  ON c.tenant_id = s.tenant_id AND c.cdp_profile_id = s.cdp_profile_id;


-- ----------------------------------------------------------------------------
-- 3. XU HƯỚNG THEO NHÓM THẾ HỆ (biểu đồ đường)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_cohort_trend WITH (security_invoker = true) AS
SELECT
    tenant_id,
    cohort,
    step_no,
    COUNT(DISTINCT user_id)                                            AS so_nguoi,
    ROUND(AVG(tg)::numeric, 4)                                         AS tg_tb,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tg))::numeric, 4) AS tg_trung_vi,
    ROUND(AVG(pas)::numeric, 4)                                        AS pas_tb,
    ROUND(100.0 * COUNT(*) FILTER (WHERE tg <= 0.05) / NULLIF(COUNT(*), 0), 1) AS pct_dat_muc_tieu
FROM v_persona_trajectory
GROUP BY tenant_id, cohort, step_no;


-- ----------------------------------------------------------------------------
-- 4. HEATMAP CHIỀU: giá trị, mục tiêu, khoảng lệch theo từng chiều của từng state
-- Chiều lấy từ persona_schemas.dimensions theo thứ tự mảng (1-based như mean[]).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_dimension_gap WITH (security_invoker = true) AS
SELECT
    st.tenant_id,
    st.user_id,
    st.cdp_profile_id,
    st.id AS state_id,
    st.as_of::date AS state_date,
    st.goal_id,
    d.ord::int AS dim_pos,
    d.code,
    d.name AS ten_chieu,
    d.direction,
    st.mean[d.ord] AS gia_tri,
    g.setpoint_min[d.ord] AS muc_tieu_min,
    g.setpoint_max[d.ord] AS muc_tieu_max,
    st.evidence_coverage[d.ord] AS do_phu_bang_chung,
    GREATEST(0, g.setpoint_min[d.ord] - st.mean[d.ord], st.mean[d.ord] - g.setpoint_max[d.ord]) AS gap,
    (st.evidence_coverage[d.ord] >= 0.4 AND g.dim_mask[d.ord] > 0) AS trong_pham_vi
FROM persona_states st
JOIN persona_goals g
  ON g.tenant_id = st.tenant_id AND g.id = st.goal_id
JOIN persona_schemas sc
  ON sc.tenant_id = st.tenant_id AND sc.id = st.schema_id
CROSS JOIN LATERAL (
    SELECT e.value->>'code' AS code,
           e.value->>'name' AS name,
           e.value->>'direction' AS direction,
           e.ord
    FROM jsonb_array_elements(sc.dimensions) WITH ORDINALITY AS e(value, ord)
) d;


-- ----------------------------------------------------------------------------
-- 5. TRẠNG THÁI MỤC TIÊU HIỆN TẠI (bảng chi tiết cho từng người)
-- Chỉ lấy mục tiêu đang hoạt động (confirmed hoặc paused).
-- dang_dung_lai: TV <= 0 ở state gần nhất, tức khoảng cách không còn thu hẹp.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_goal_status WITH (security_invoker = true) AS
WITH latest AS (
    SELECT DISTINCT ON (tenant_id, user_id, goal_id) *
    FROM v_persona_trajectory
    ORDER BY tenant_id, user_id, goal_id, state_date DESC, step_no DESC
),
first_t AS (
    SELECT DISTINCT ON (tenant_id, user_id, goal_id)
           tenant_id, user_id, goal_id, tg AS tg_ban_dau
    FROM v_persona_trajectory
    ORDER BY tenant_id, user_id, goal_id, state_date ASC, step_no ASC
)
SELECT
    l.tenant_id,
    l.user_id,
    l.cdp_profile_id,
    l.cohort,
    l.goal_id,
    g.title AS muc_tieu,
    g.version,
    g.status AS trang_thai_muc_tieu,
    l.state_date AS ngay_gan_nhat,
    f.tg_ban_dau,
    l.tg AS tg_hien_tai,
    ROUND((f.tg_ban_dau - l.tg)::numeric, 4) AS da_thu_hep,
    l.tv,
    l.band AS muc_do,
    (l.tv IS NOT NULL AND l.tv <= 0) AS dang_dung_lai
FROM latest l
JOIN first_t f USING (tenant_id, user_id, goal_id)
JOIN persona_goals g ON g.tenant_id = l.tenant_id AND g.id = l.goal_id
WHERE g.status IN ('confirmed', 'paused');


-- ----------------------------------------------------------------------------
-- 6. KẾT QUẢ CỦA TỪNG QUYẾT ĐỊNH (một dòng mỗi quyết định)
-- Gom outcome theo quyết định bằng cờ, tránh đếm trùng khi nối nhiều dòng phản hồi.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reco_decision_outcome WITH (security_invoker = true) AS
SELECT
    d.tenant_id,
    d.id AS decision_id,
    d.user_id,
    st.cdp_profile_id,
    d.proposed_at,
    d.chosen_item_id AS item_id,
    d.chosen_kind,
    d.guardrail_result,
    d.is_exploration,
    d.executed_at IS NOT NULL AS executed,
    COALESCE(BOOL_OR(o.event_type = 'delivered'), FALSE)                    AS delivered,
    COALESCE(BOOL_OR(o.event_type IN ('accepted', 'completed')), FALSE)     AS accepted,
    COALESCE(BOOL_OR(o.event_type = 'dismissed'), FALSE)                    AS dismissed,
    COALESCE(BOOL_OR(o.event_type = 'harm_report'), FALSE)                  AS had_harm,
    AVG(o.participant_rating)                                               AS rating_avg
FROM recommendation_decisions d
LEFT JOIN persona_states st
       ON st.tenant_id = d.tenant_id AND st.id = d.state_id
LEFT JOIN recommendation_outcomes o
       ON o.tenant_id = d.tenant_id AND o.decision_id = d.id
GROUP BY d.tenant_id, d.id, d.user_id, st.cdp_profile_id, d.proposed_at, d.chosen_item_id,
         d.chosen_kind, d.guardrail_result, d.is_exploration, d.executed_at;


-- ----------------------------------------------------------------------------
-- 7. HIỆU QUẢ THEO TỪNG MỤC GỢI Ý (biểu đồ cột, bảng xếp hạng)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reco_item_performance WITH (security_invoker = true) AS
SELECT
    i.tenant_id,
    i.id AS item_id,
    i.action_kind,
    i.title,
    i.ref_table,
    COUNT(o.decision_id)                                                    AS so_lan_duoc_chon,
    COUNT(*) FILTER (WHERE o.executed)                                      AS so_lan_da_gui,
    COUNT(*) FILTER (WHERE o.delivered)                                     AS so_lan_da_nhan,
    COUNT(*) FILTER (WHERE o.accepted)                                      AS so_lan_chap_nhan,
    COUNT(*) FILTER (WHERE o.dismissed)                                     AS so_lan_bo_qua,
    COUNT(*) FILTER (WHERE o.had_harm)                                      AS so_bao_cao_gay_hai,
    ROUND(AVG(o.rating_avg)::numeric, 2)                                    AS danh_gia_tb,
    ROUND(100.0 * COUNT(*) FILTER (WHERE o.accepted)
          / NULLIF(COUNT(*) FILTER (WHERE o.delivered), 0), 1)              AS pct_chap_nhan,
    ROUND(100.0 * COUNT(*) FILTER (WHERE o.had_harm)
          / NULLIF(COUNT(*) FILTER (WHERE o.delivered), 0), 1)              AS pct_gay_hai
FROM recommendation_items i
LEFT JOIN v_reco_decision_outcome o
       ON o.tenant_id = i.tenant_id AND o.item_id = i.id
GROUP BY i.tenant_id, i.id, i.action_kind, i.title, i.ref_table;


-- ----------------------------------------------------------------------------
-- 8. LÝ DO BỊ LOẠI (biểu đồ thanh: vì sao bot không chọn mục nào đó)
-- Lấy loại lý do từ excluded_by, bỏ phần đuôi (ví dụ low_evidence_coverage_R -> low_evidence_coverage).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reco_exclusion_reasons WITH (security_invoker = true) AS
SELECT
    d.tenant_id,
    REGEXP_REPLACE(SPLIT_PART(c->>'excluded_by', ':', 1), '_[A-Z]+$', '') AS ly_do,
    COUNT(*) AS so_lan
FROM recommendation_decisions d
CROSS JOIN LATERAL jsonb_array_elements(d.candidates) AS c
WHERE c->>'excluded_by' IS NOT NULL
GROUP BY d.tenant_id, 2;


-- ----------------------------------------------------------------------------
-- 9. XU HƯỚNG GỢI Ý THEO NGÀY (biểu đồ đường)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reco_daily WITH (security_invoker = true) AS
SELECT
    tenant_id,
    proposed_at::date AS ngay,
    COUNT(*) AS so_quyet_dinh,
    COUNT(*) FILTER (WHERE executed) AS so_da_gui,
    COUNT(*) FILTER (WHERE chosen_kind = 'no_action') AS so_khong_lam_gi,
    COUNT(*) FILTER (WHERE accepted) AS so_chap_nhan,
    COUNT(*) FILTER (WHERE had_harm) AS so_bao_cao_gay_hai,
    COUNT(*) FILTER (WHERE guardrail_result <> 'allowed') AS so_can_xem_xet
FROM v_reco_decision_outcome
GROUP BY tenant_id, proposed_at::date;


-- ----------------------------------------------------------------------------
-- 10. CONSENT: sức khỏe của sự đồng ý theo từng phạm vi
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_consent_health WITH (security_invoker = true) AS
WITH rut30 AS (
    SELECT tenant_id, scope_type, scope_key, purpose, COUNT(*) AS so_rut_30_ngay
    FROM persona_consents
    WHERE status = 'withdrawn' AND effective_at >= NOW() - INTERVAL '30 days'
    GROUP BY tenant_id, scope_type, scope_key, purpose
)
SELECT
    cur.tenant_id,
    cur.scope_type,
    cur.scope_key,
    cur.purpose,
    COUNT(*) AS tong_nguoi,
    COUNT(*) FILTER (WHERE cur.status = 'granted'
                     AND (cur.expires_at IS NULL OR cur.expires_at > NOW())) AS dang_dong_y,
    COUNT(*) FILTER (WHERE cur.status = 'granted' AND cur.expires_at <= NOW()) AS het_han,
    COUNT(*) FILTER (WHERE cur.status = 'declined') AS tu_choi,
    COUNT(*) FILTER (WHERE cur.status = 'withdrawn') AS da_rut,
    COALESCE(MAX(r.so_rut_30_ngay), 0) AS so_rut_30_ngay
FROM persona_consents_current cur
LEFT JOIN rut30 r
       ON r.tenant_id = cur.tenant_id AND r.scope_type = cur.scope_type
      AND r.scope_key = cur.scope_key AND r.purpose = cur.purpose
GROUP BY cur.tenant_id, cur.scope_type, cur.scope_key, cur.purpose;


-- ----------------------------------------------------------------------------
-- 11. CHẤT LƯỢNG BẰNG CHỨNG: cơ cấu nguồn theo từng chiều
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_evidence_quality WITH (security_invoker = true) AS
SELECT
    tenant_id,
    dimension_code,
    kind,
    COUNT(*) AS so_dong,
    COUNT(*) FILTER (WHERE retracted_at IS NOT NULL) AS da_thu_hoi,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY tenant_id, dimension_code), 1) AS pct_trong_chieu
FROM persona_evidence
GROUP BY tenant_id, dimension_code, kind;


-- ----------------------------------------------------------------------------
-- 12. PANEL CHẤT LƯỢNG DỮ LIỆU: mỗi kiểm tra một dòng cho mỗi tenant
-- Kỳ vọng so_loi = 0. Khác 0 là có vấn đề cần xem.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_dq_checks WITH (security_invoker = true) AS
WITH t AS (
    SELECT DISTINCT tenant_id FROM persona_goals
),
c1 AS (  -- bằng chứng có event_time sau as_of của state
    SELECT s.tenant_id, COUNT(*) AS n
    FROM persona_states s
    JOIN persona_evidence e ON e.tenant_id = s.tenant_id AND e.id = ANY (s.evidence_ids)
    WHERE e.event_time > s.as_of
    GROUP BY s.tenant_id
),
c2 AS (  -- bằng chứng đã thu hồi nhưng vẫn nằm trong state tính sau thời điểm thu hồi
    SELECT s.tenant_id, COUNT(*) AS n
    FROM persona_states s
    JOIN persona_evidence e ON e.tenant_id = s.tenant_id AND e.id = ANY (s.evidence_ids)
    WHERE e.retracted_at IS NOT NULL AND e.retracted_at <= s.as_of
    GROUP BY s.tenant_id
),
c3 AS (  -- state không có snapshot khoảng cách
    SELECT s.tenant_id, COUNT(*) AS n
    FROM persona_states s
    WHERE NOT EXISTS (
        SELECT 1 FROM persona_gap_snapshots g
        WHERE g.tenant_id = s.tenant_id AND g.state_id = s.id AND NOT g.is_reanalysis)
    GROUP BY s.tenant_id
),
c4 AS (  -- quyết định chọn một mục đã bị loại trong danh sách ứng viên
    SELECT d.tenant_id, COUNT(*) AS n
    FROM recommendation_decisions d
    WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements(d.candidates) c
        WHERE c->>'item_id' = d.chosen_item_id::text AND c->>'excluded_by' IS NOT NULL)
    GROUP BY d.tenant_id
),
c5 AS (  -- đã gửi nhưng consent không hợp lệ tại thời điểm gửi
    SELECT d.tenant_id, COUNT(*) AS n
    FROM recommendation_decisions d
    WHERE d.executed_at IS NOT NULL
      AND COALESCE((d.execution_check->>'consent_ok')::boolean, FALSE) = FALSE
    GROUP BY d.tenant_id
),
c6 AS (  -- cần người duyệt nhưng đã gửi mà không có người duyệt
    SELECT d.tenant_id, COUNT(*) AS n
    FROM recommendation_decisions d
    WHERE d.guardrail_result = 'needs_review' AND d.executed_at IS NOT NULL
      AND d.execution_check->>'reviewer' IS NULL
    GROUP BY d.tenant_id
),
c7 AS (  -- phản hồi xảy ra trước thời điểm đề xuất
    SELECT o.tenant_id, COUNT(*) AS n
    FROM recommendation_outcomes o
    JOIN recommendation_decisions d ON d.tenant_id = o.tenant_id AND d.id = o.decision_id
    WHERE o.occurred_at < d.proposed_at
    GROUP BY o.tenant_id
),
checks AS (
    SELECT 'Bằng chứng sau thời điểm state' AS kiem_tra, 'c1' AS ma
    UNION ALL SELECT 'Bằng chứng đã thu hồi còn trong state mới', 'c2'
    UNION ALL SELECT 'State thiếu snapshot khoảng cách', 'c3'
    UNION ALL SELECT 'Quyết định chọn mục đã bị loại', 'c4'
    UNION ALL SELECT 'Đã gửi khi consent không hợp lệ', 'c5'
    UNION ALL SELECT 'Cần duyệt nhưng gửi không có người duyệt', 'c6'
    UNION ALL SELECT 'Phản hồi trước thời điểm đề xuất', 'c7'
),
counts AS (
    SELECT t.tenant_id, ch.kiem_tra, ch.ma,
           CASE ch.ma
             WHEN 'c1' THEN (SELECT n FROM c1 WHERE c1.tenant_id = t.tenant_id)
             WHEN 'c2' THEN (SELECT n FROM c2 WHERE c2.tenant_id = t.tenant_id)
             WHEN 'c3' THEN (SELECT n FROM c3 WHERE c3.tenant_id = t.tenant_id)
             WHEN 'c4' THEN (SELECT n FROM c4 WHERE c4.tenant_id = t.tenant_id)
             WHEN 'c5' THEN (SELECT n FROM c5 WHERE c5.tenant_id = t.tenant_id)
             WHEN 'c6' THEN (SELECT n FROM c6 WHERE c6.tenant_id = t.tenant_id)
             WHEN 'c7' THEN (SELECT n FROM c7 WHERE c7.tenant_id = t.tenant_id)
           END AS n
    FROM t CROSS JOIN checks ch
)
SELECT tenant_id, kiem_tra, COALESCE(n, 0) AS so_loi,
       CASE WHEN COALESCE(n, 0) = 0 THEN 'OK' ELSE 'CẦN XEM' END AS trang_thai
FROM counts;


-- ----------------------------------------------------------------------------
-- 13. THẺ KPI: một dòng cho mỗi tenant (thẻ đầu trang dashboard)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_persona_kpi_overview WITH (security_invoker = true) AS
WITH goals AS (
    SELECT tenant_id,
           COUNT(DISTINCT user_id) AS nguoi_co_muc_tieu,
           COUNT(*) AS muc_tieu_theo_doi,
           ROUND(AVG(tg_hien_tai)::numeric, 4) AS tg_tb_hien_tai,
           ROUND(100.0 * COUNT(*) FILTER (WHERE tg_hien_tai <= 0.05) / NULLIF(COUNT(*), 0), 1) AS pct_dat_muc_tieu,
           COUNT(*) FILTER (WHERE dang_dung_lai) AS so_dang_dung_lai
    FROM v_persona_goal_status
    GROUP BY tenant_id
),
reco AS (
    SELECT tenant_id,
           COUNT(*) AS quyet_dinh_30_ngay,
           COUNT(*) FILTER (WHERE executed) AS da_gui_30_ngay,
           ROUND(100.0 * COUNT(*) FILTER (WHERE accepted)
                 / NULLIF(COUNT(*) FILTER (WHERE delivered), 0), 1) AS pct_chap_nhan_30_ngay,
           COUNT(*) FILTER (WHERE had_harm) AS bao_cao_gay_hai_30_ngay
    FROM v_reco_decision_outcome
    WHERE proposed_at >= NOW() - INTERVAL '30 days'
    GROUP BY tenant_id
),
rut AS (
    SELECT tenant_id, COUNT(*) AS rut_dong_y_30_ngay
    FROM persona_consents
    WHERE status = 'withdrawn' AND effective_at >= NOW() - INTERVAL '30 days'
    GROUP BY tenant_id
),
dq AS (
    SELECT tenant_id, COUNT(*) FILTER (WHERE so_loi > 0) AS so_kiem_tra_can_xem
    FROM v_persona_dq_checks
    GROUP BY tenant_id
),
t AS (SELECT DISTINCT tenant_id FROM persona_goals)
SELECT
    t.tenant_id,
    COALESCE(goals.nguoi_co_muc_tieu, 0)      AS nguoi_co_muc_tieu,
    COALESCE(goals.muc_tieu_theo_doi, 0)      AS muc_tieu_theo_doi,
    goals.tg_tb_hien_tai,
    goals.pct_dat_muc_tieu,
    COALESCE(goals.so_dang_dung_lai, 0)       AS so_dang_dung_lai,
    COALESCE(reco.quyet_dinh_30_ngay, 0)      AS quyet_dinh_30_ngay,
    COALESCE(reco.da_gui_30_ngay, 0)          AS da_gui_30_ngay,
    reco.pct_chap_nhan_30_ngay,
    COALESCE(reco.bao_cao_gay_hai_30_ngay, 0) AS bao_cao_gay_hai_30_ngay,
    COALESCE(rut.rut_dong_y_30_ngay, 0)       AS rut_dong_y_30_ngay,
    COALESCE(dq.so_kiem_tra_can_xem, 0)       AS kiem_tra_dq_can_xem
FROM t
LEFT JOIN goals ON goals.tenant_id = t.tenant_id
LEFT JOIN reco  ON reco.tenant_id  = t.tenant_id
LEFT JOIN rut   ON rut.tenant_id   = t.tenant_id
LEFT JOIN dq    ON dq.tenant_id    = t.tenant_id;


-- ============================================================================
-- VÍ DỤ TRUY VẤN CHO TỪNG WIDGET (thay 'leo_travel' bằng tenant thật)
-- ============================================================================
-- Thẻ KPI
-- SELECT * FROM v_persona_kpi_overview WHERE tenant_id = 'leo_travel';

-- Đường xu hướng TG theo thế hệ
-- SELECT cohort, step_no, tg_tb, tg_trung_vi, pct_dat_muc_tieu
-- FROM v_persona_cohort_trend WHERE tenant_id = 'leo_travel' ORDER BY cohort, step_no;

-- Heatmap chiều (giá trị và khoảng lệch) cho state gần nhất của mỗi người
-- SELECT DISTINCT ON (user_id, goal_id, code) user_id, code, ten_chieu, gia_tri, gap, trong_pham_vi
-- FROM v_persona_dimension_gap WHERE tenant_id = 'leo_travel'
-- ORDER BY user_id, goal_id, code, state_date DESC;

-- Bảng trạng thái mục tiêu, sắp xếp theo khoảng cách còn lại
-- SELECT cohort, muc_tieu, tg_ban_dau, tg_hien_tai, da_thu_hep, muc_do, dang_dung_lai
-- FROM v_persona_goal_status WHERE tenant_id = 'leo_travel' ORDER BY tg_hien_tai;

-- Bảng xếp hạng gợi ý
-- SELECT title, action_kind, so_lan_da_gui, pct_chap_nhan, pct_gay_hai, danh_gia_tb
-- FROM v_reco_item_performance WHERE tenant_id = 'leo_travel' ORDER BY pct_chap_nhan DESC NULLS LAST;

-- Lý do bị loại
-- SELECT ly_do, so_lan FROM v_reco_exclusion_reasons WHERE tenant_id = 'leo_travel' ORDER BY so_lan DESC;

-- Xu hướng gợi ý theo ngày
-- SELECT ngay, so_quyet_dinh, so_da_gui, so_chap_nhan, so_bao_cao_gay_hai
-- FROM v_reco_daily WHERE tenant_id = 'leo_travel' ORDER BY ngay;

-- Consent
-- SELECT scope_type, scope_key, purpose, dang_dong_y, het_han, tu_choi, da_rut, so_rut_30_ngay
-- FROM v_persona_consent_health WHERE tenant_id = 'leo_travel';

-- Panel chất lượng dữ liệu
-- SELECT kiem_tra, so_loi, trang_thai FROM v_persona_dq_checks WHERE tenant_id = 'leo_travel' ORDER BY so_loi DESC;
