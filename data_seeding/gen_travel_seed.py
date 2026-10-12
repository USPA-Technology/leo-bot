#!/usr/bin/env python3
"""
Sinh dữ liệu seed cho TOÀN BỘ bảng SQL, tenant 'leo_travel', chỉ lĩnh vực du lịch.
Persona: từ "ít trải nghiệm mới, lịch trình lặp lại" sang "vui hơn, nhiều kỷ niệm"
cho 3 thế hệ: 1970-1982, 1983-1995, 1996-2008.

Toàn bộ dữ liệu là tổng hợp (synthetic). Embedding là vector giả để kiểm thử
truy vấn, KHÔNG có ý nghĩa ngữ nghĩa.

Cách dùng:  python3 gen_travel_seed.py travel_seed_all_tables.sql
"""
import json, math, sys, uuid, datetime as dt

TENANT = "leo_travel"
TZ = dt.timezone(dt.timedelta(hours=7))
TODAY = dt.date(2026, 10, 12)
NS = uuid.UUID("3b1f6c2e-9a4d-4f7e-8c21-5d0e7a9b1f01")
DIMS = ["NV", "SC", "PF", "MM"]
DIM_IDX = {d: i for i, d in enumerate(DIMS)}
DIST_VERSION = "dist-travel-v1"
MODEL_VERSION = "persona-est-travel-v1"
POLICY = "travel-nba-v1"
PD_THRESHOLD = 0.35
COVERAGE_MIN = 0.4


def U(name):
    return str(uuid.uuid5(NS, name))


def P(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=TZ)


def D(s):
    return dt.date.fromisoformat(s)


def age_on(birth, on):
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


# ---------------- SQL helpers ----------------
def q(s):
    return "'" + str(s).replace("'", "''") + "'"


def ts(x):
    return "NULL" if x is None else q(x.isoformat())


def jb(o):
    return q(json.dumps(o, ensure_ascii=False)) + "::jsonb"


def txa(a):
    return ("ARRAY[" + ",".join(q(x) for x in a) + "]::text[]") if a else "'{}'::text[]"


def rla(a):
    return "ARRAY[" + ",".join(repr(round(float(x), 4)) for x in a) + "]::real[]"


def uua(a):
    return ("ARRAY[" + ",".join(q(x) for x in a) + "]::uuid[]") if a else "'{}'::uuid[]"


def vec(seed):
    return f"seed_vec768({q(seed)})"


def nn(x):
    if x is None:
        return "NULL"
    if isinstance(x, bool):
        return "TRUE" if x else "FALSE"
    if isinstance(x, float):
        return repr(round(x, 6))
    return str(x)


def ins(table, cols, rows, tail=";"):
    if not rows:
        return ""
    body = ",\n".join("  (" + ", ".join(r) + ")" for r in rows)
    return f"INSERT INTO {table} ({', '.join(cols)})\nVALUES\n{body}{tail}\n"


# ---------------- Cấu hình thế hệ ----------------
GEN = {
    "G1": dict(cohort="1970–1982", lo=[0.4, 0.5, 0.4, 0.5], hi=[0.8, 1.0, 0.7, 1.0], mask=[0.5, 1, 1, 1],
               title="Chuyến đi có vài điều mới nhưng vẫn thư thả",
               bound={"nhac_truoc_21h": True, "khong_lich_day_dac": True}, budget=8000000),
    "G2": dict(cohort="1983–1995", lo=[0.6, 0.4, 0.4, 0.6], hi=[1.0, 0.9, 0.7, 1.0], mask=[1, 0.5, 1, 1],
               title="Khám phá nhiều điều mới trong mỗi chuyến đi",
               bound={"khong_nhac_sau": "21:00"}, budget=6000000),
    "G3": dict(cohort="1996–2008", lo=[0.7, 0.7, 0.3, 0.5], hi=[1.0, 1.0, 0.6, 1.0], mask=[1, 1, 0.5, 1],
               title="Đi cùng bạn bè, nhiều kỷ niệm với ngân sách vừa phải",
               bound={"khong_nhac_sau": "22:00", "ngan_sach_vnd_toi_da": 4000000}, budget=3500000),
}
LEGACY = {
    "g1_03": dict(lo=[0.2, 0.2, 0.5, 0.3], hi=[0.5, 0.5, 0.8, 0.7], mask=[0.5, 0.5, 1, 0.5],
                  title="Nghỉ ngơi yên tĩnh, ít lịch trình", confirmed="2026-04-15 11:00", until=2),
    "g2_02": dict(lo=[0.2, 0.7, 0.3, 0.3], hi=[0.5, 1.0, 0.6, 0.7], mask=[0.5, 1, 1, 0.5],
                  title="Đi cùng gia đình, thư giãn", confirmed="2026-02-20 11:00", until=2),
}

# ---------------- Người dùng tổng hợp ----------------
# states: (ngày, [NV, SC, PF, MM], [coverage NV, SC, PF, MM])
USERS = [
    dict(key="g1_01", gen="G1", name="Nguyễn Thị Lan", birth="1971-03-14", loc=True,
         city="Đà Lạt", ll=(11.9404, 108.4583), channel="webchat",
         msgs=("Năm nào gia đình tôi cũng đi đúng một lịch trình cũ, nên chuyến đi không còn điều gì mới.",
               "Chuyến tới tôi muốn có vài điều mới nhưng vẫn đi thong thả."),
         words="Muốn chuyến đi có điều mới mà không phải chạy theo lịch kín mít",
         states=[("2025-11-05", [0.20, 0.30, 0.85, 0.20], [0.9, 0.8, 0.9, 0.25]),
                 ("2026-03-20", [0.45, 0.45, 0.70, 0.40], [0.9, 0.8, 0.9, 0.6]),
                 ("2026-08-30", [0.65, 0.70, 0.60, 0.75], [0.9, 0.9, 0.9, 0.8])]),
    dict(key="g1_02", gen="G1", name="Trần Văn Hùng", birth="1978-07-02", loc=True,
         city="Hội An", ll=(15.8801, 108.3380), channel="webchat",
         msgs=("Mỗi lần đi Hội An tôi vẫn ở cùng một quán và đi cùng một tuyến, không có gì thay đổi.",
               "Tôi muốn gặp thêm vài người mới trên đường đi, không cần đi quá xa."),
         words="Muốn đi lại một mình nhưng có thêm người để trò chuyện",
         explore=2,
         states=[("2025-12-02", [0.10, 0.10, 0.50, 0.15], [0.8, 0.9, 0.7, 0.2]),
                 ("2026-02-14", [0.35, 0.40, 0.55, 0.35], [0.8, 0.8, 0.8, 0.5]),
                 ("2026-09-01", [0.55, 0.65, 0.60, 0.60], [0.9, 0.9, 0.9, 0.8])]),
    dict(key="g1_03", gen="G1", name="Lê Thị Mai", birth="1982-11-20", loc=False, channel="webchat",
         msgs=("Chuyến công tác nào tôi cũng chỉ ở khách sạn rồi về, không có thời gian khám phá.",
               "Lần nghỉ tới tôi muốn đi một nơi mới, có vài hoạt động nhẹ."),
         words="Muốn nghỉ ngơi nhưng cũng muốn đi một nơi chưa từng đến",
         states=[("2025-10-28", [0.25, 0.20, 0.30, 0.10], [0.9, 0.6, 0.8, 0.3]),
                 ("2026-04-10", [0.40, 0.35, 0.45, 0.30], [0.9, 0.7, 0.9, 0.5]),
                 ("2026-10-01", [0.60, 0.55, 0.55, 0.65], [0.9, 0.8, 0.9, 0.8])]),
    dict(key="g2_01", gen="G2", name="Phạm Minh Khang", birth="1990-05-09", loc=True,
         city="Phú Quốc", ll=(10.2899, 103.9840), channel="zalo",
         msgs=("Cuối tuần nào nhóm bạn cũng đi cùng một resort, ăn uống và nghỉ như cũ.",
               "Tôi muốn thử món mới và đi những nơi chưa từng đến."),
         words="Muốn thử món mới và đi những nơi chưa từng đến",
         states=[("2025-11-22", [0.15, 0.50, 0.60, 0.20], [0.9, 0.9, 0.8, 0.4]),
                 ("2026-01-18", [0.40, 0.60, 0.65, 0.40], [0.9, 0.9, 0.9, 0.7]),
                 ("2026-07-25", [0.75, 0.70, 0.60, 0.80], [0.9, 0.9, 0.9, 0.9])]),
    dict(key="g2_02", gen="G2", name="Võ Thu Hà", birth="1986-02-27", loc=True,
         city="Sa Pa", ll=(22.3364, 103.8438), channel="webchat",
         msgs=("Cả nhà đi Sa Pa vẫn theo kế hoạch cũ, các con ít khi được chọn hoạt động.",
               "Năm nay tôi muốn cả nhà cùng làm một việc mới, không chỉ ngồi nghỉ."),
         words="Cả nhà cùng làm một việc mới, không chỉ nghỉ ngơi",
         explore=None,
         states=[("2025-12-20", [0.30, 0.80, 0.20, 0.25], [0.8, 0.9, 0.6, 0.5]),
                 ("2026-02-10", [0.45, 0.85, 0.35, 0.45], [0.9, 0.9, 0.7, 0.7]),
                 ("2026-09-15", [0.70, 0.80, 0.55, 0.85], [0.9, 0.9, 0.9, 0.9])]),
    dict(key="g2_03", gen="G2", name="Đặng Quốc Bảo", birth="1994-09-03", loc=False, channel="zalo",
         withdraw=True,
         msgs=("Tôi làm việc ở một quán cà phê quen mỗi tuần, chuyến đi cũng chỉ là đổi quán.",
               "Tôi muốn một chuyến đi có người mới và vài trải nghiệm đáng nhớ."),
         words="Muốn một chuyến đi có người mới và vài trải nghiệm đáng nhớ",
         states=[("2025-10-30", [0.10, 0.25, 0.45, 0.10], [0.9, 0.7, 0.9, 0.2]),
                 ("2026-03-02", [0.50, 0.40, 0.50, 0.35], [0.9, 0.8, 0.9, 0.5]),
                 ("2026-08-05", [0.80, 0.55, 0.60, 0.70], [0.9, 0.9, 0.9, 0.8])]),
    dict(key="g3_01", gen="G3", name="Hoàng Gia Huy", birth="2001-04-18", loc=True,
         city="Hạ Long", ll=(20.9101, 107.1839), channel="zalo",
         msgs=("Cả nhóm bạn lần nào đi Hạ Long cũng tự làm việc riêng, ít khi đi chung.",
               "Lần tới tôi muốn cùng làm một hoạt động chung và chụp vài khoảnh khắc đẹp."),
         words="Muốn cùng bạn bè làm một hoạt động chung",
         states=[("2025-12-10", [0.20, 0.15, 0.65, 0.10], [0.8, 0.6, 0.7, 0.3]),
                 ("2026-02-01", [0.45, 0.40, 0.55, 0.35], [0.9, 0.8, 0.8, 0.6]),
                 ("2026-09-10", [0.75, 0.80, 0.50, 0.70], [0.9, 0.9, 0.9, 0.9])]),
    dict(key="g3_02", gen="G3", name="Bùi Khánh Linh", birth="2005-10-30", loc=True,
         city="Huế", ll=(16.4637, 107.5909), channel="webchat", retract_nv=True,
         msgs=("Chuyến Huế tháng trước tôi ghi nhầm một chuyến hai lần, nhờ sửa giúp.",
               "Tôi muốn chuyến tới đi với bạn bè, ngân sách vừa phải và có nhiều điều mới."),
         words="Đi với bạn bè, ngân sách vừa phải, có nhiều điều mới",
         states=[("2025-11-15", [0.30, 0.20, 0.40, 0.15], [0.8, 0.7, 0.8, 0.5]),
                 ("2026-05-20", [0.55, 0.45, 0.50, 0.45], [0.9, 0.9, 0.9, 0.7]),
                 ("2026-10-02", [0.70, 0.75, 0.55, 0.60], [0.9, 0.9, 0.9, 0.8])]),
    dict(key="g3_03", gen="G3", name="Ngô Bảo Trân", birth="2008-06-15", loc=False, channel="webchat",
         harm_at=2,
         msgs=("Chuyến đi nào lịch cũng kín từ sáng đến tối, tôi chỉ muốn ít việc hơn.",
               "Lần sau tôi muốn đi ít điểm hơn, nhưng có một hoạt động nhóm nho nhỏ."),
         words="Đi ít điểm hơn nhưng có một hoạt động nhóm nho nhỏ",
         states=[("2025-11-28", [0.10, 0.10, 0.30, 0.05], [0.6, 0.5, 0.6, 0.2]),
                 ("2026-03-28", [0.35, 0.40, 0.40, 0.30], [0.8, 0.8, 0.8, 0.5]),
                 ("2026-09-28", [0.65, 0.70, 0.50, 0.55], [0.9, 0.9, 0.9, 0.8])]),
]

DESTS = ["Đà Lạt", "Hội An", "Phú Quốc", "Sa Pa", "Hạ Long", "Huế", "Phong Nha", "Mũi Né"]

KNOWLEDGE = [
    ("bat_ngo", "Vì sao điều bất ngờ nhỏ làm chuyến đi đáng nhớ hơn", [
        "Trí nhớ về chuyến đi thường bám vào vài khoảnh khắc khác thường hơn là lịch trình đều đặn. Một việc nhỏ ngoài dự kiến có thể tạo khác biệt.",
        "Điều bất ngờ nên đủ nhỏ để không làm mất cảm giác an toàn. Chọn một khung giờ trống và để người đi cùng quyết định hoạt động."]),
    ("g1", "Cẩm nang du lịch chậm cho thế hệ 1970–1982", [
        "Nhiều người sinh giai đoạn này đã quen với chuyến đi theo kế hoạch cứng. Khi đổi sang nhịp chậm, nên giữ một hoạt động quen và thêm một điểm mới.",
        "Với chuyến đi gia đình, nên để một buổi sáng không có lịch. Thời gian trống giúp mọi người trò chuyện nhiều hơn."]),
    ("g2", "Cẩm nang khám phá cho thế hệ 1983–1995", [
        "Chuyến đi cuối tuần thường lặp lại một địa điểm quen. Thử đổi một yếu tố mỗi chuyến: món ăn, tuyến đường hoặc cách di chuyển.",
        "Ghi chú ngắn sau mỗi chuyến, như ba điều đã thấy và một điều muốn thử lần sau, giúp nhìn lại trải nghiệm rõ hơn."]),
    ("g3", "Cẩm nang du lịch xã hội cho thế hệ 1996–2008", [
        "Đi cùng bạn bè vẫn dễ thành mỗi người một việc. Một hoạt động chung như nấu ăn hoặc đi bộ phố cũ giúp nhóm gắn kết hơn.",
        "Ngân sách vừa phải không đồng nghĩa với ít trải nghiệm. Chọn một trải nghiệm đáng tiền mỗi chuyến và tiết kiệm phần còn lại."]),
    ("dalat", "Đà Lạt: nhịp chậm trên đồi thông", [
        "Buổi sáng ở hồ Xuân Hương thường yên tĩnh hơn. Nên đến sớm để đi bộ quanh hồ trước khi đông khách.",
        "Buổi chiều trên đồi chè hợp với nhịp chậm. Chỉ nên chọn hai điểm trong một buổi để không mệt."]),
    ("hoian", "Hội An: đi bộ phố cổ buổi tối", [
        "Phố cổ đẹp nhất khi đèn lồng lên. Nên đi bộ không cần đích đến và thử một món địa phương mỗi tối.",
        "Đi thuyền trên sông Hoài buổi tối phù hợp với nhóm nhỏ, giúp trò chuyện nhiều hơn."]),
    ("halong", "Hạ Long: một buổi chiều trên vịnh", [
        "Chuyến tàu nửa ngày đủ để ngắm vịnh mà không mất nhiều thời gian. Chọn khoang ngoài trời để có nhiều khoảnh khắc đẹp.",
        "Người đi lần đầu nên chọn chuyến có hướng dẫn viên để hiểu thêm về các địa danh trên vịnh."]),
]

GEO = [
    ("dalat_xuanhuong", "Hồ Xuân Hương, Đà Lạt", "Lâm Đồng", "VN-LAM-DONG", 11.9440, 108.4430, 4.6, 5120,
     "Hồ trung tâm thành phố, phù hợp đi bộ buổi sáng.", ["thien_nhien", "thu_gian"]),
    ("hoian_phocotuoi", "Phố cổ Hội An", "Quảng Nam", "VN-QUANG-NAM", 15.8778, 108.3260, 4.7, 9800,
     "Khu phố cổ có đèn lồng, thích hợp đi bộ buổi tối.", ["van_hoa", "am_thuc"]),
    ("phuquoc_baosao", "Khu vực Bãi Sao, Phú Quốc", "Kiên Giang", "VN-KIEN-GIANG", 10.2899, 103.9840, 4.5, 4300,
     "Bãi biển yên tĩnh phía nam đảo.", ["bien", "thu_gian"]),
    ("sapa_catcat", "Bản Cát Cát, Sa Pa", "Lào Cai", "VN-LAO-CAI", 22.3364, 103.8438, 4.5, 3900,
     "Bản làng dọc suối, đi bộ nhẹ nhàng.", ["thien_nhien", "van_hoa"]),
    ("halong_baitulong", "Vịnh Hạ Long khu Bãi Tử Long", "Quảng Ninh", "VN-QUANG-NINH", 20.9101, 107.1839, 4.6, 8700,
     "Đi tàu ngắm vịnh, có khoang ngoài trời.", ["bien", "chup_anh"]),
    ("hue_daineh", "Đại Nội Huế", "Thừa Thiên Huế", "VN-THUA-THIEN-HUE", 16.4698, 107.5787, 4.6, 7400,
     "Khu di tích cung đình, nên đi buổi sáng.", ["van_hoa", "lich_su"]),
    ("phongnha_kebang", "Vườn quốc gia Phong Nha - Kẻ Bàng", "Quảng Bình", "VN-QUANG-BINH", 17.5860, 106.2820, 4.7, 5600,
     "Hệ thống hang động, cần đặt tour trước.", ["thien_nhien", "mao_hiem"]),
    ("muine_doicat", "Đồi cát Mũi Né", "Bình Thuận", "VN-BINH-THUAN", 10.9333, 108.2833, 4.4, 3100,
     "Đồi cát ngắm hoàng hôn, nên đi cuối chiều.", ["thien_nhien", "chup_anh"]),
]

WEATHER = [  # (địa điểm, thành phố, lat, lng, min, max, xác suất mưa %)
    ("Đà Lạt, Lâm Đồng", "Đà Lạt", 11.9404, 108.4583, 15, 22, 60),
    ("Hội An, Quảng Nam", "Hội An", 15.8801, 108.3380, 24, 31, 40),
    ("Phú Quốc, Kiên Giang", "Phú Quốc", 10.2899, 103.9840, 25, 32, 30),
    ("Sa Pa, Lào Cai", "Sa Pa", 22.3364, 103.8438, 9, 16, 55),
    ("Hạ Long, Quảng Ninh", "Hạ Long", 20.9101, 107.1839, 22, 27, 45),
    ("Huế, Thừa Thiên Huế", "Huế", 16.4637, 107.5909, 22, 29, 50),
    ("Phong Nha, Quảng Bình", "Phong Nha", 17.5860, 106.2820, 21, 28, 55),
    ("Mũi Né, Bình Thuận", "Mũi Né", 10.9333, 108.2833, 25, 33, 20),
]

# Mục gợi ý: (mã, loại, bảng tham chiếu, khóa tham chiếu, tiêu đề, chiều, yêu cầu đồng ý, tiền điều kiện, cooldown ngày, điểm nền, cần kiểm tra coverage)
ITEMS = [
    ("bat_ngo", "explain", "knowledge_sources", "bat_ngo", "Vì sao điều bất ngờ nhỏ làm chuyến đi đáng nhớ hơn", ["MM"], [], {}, 14, 0.20, True),
    ("cam_g1", "resource", "knowledge_sources", "g1", "Cẩm nang du lịch chậm cho thế hệ 1970–1982", ["NV", "PF"], [], {}, 30, 0.30, True),
    ("cam_g2", "resource", "knowledge_sources", "g2", "Cẩm nang khám phá cho thế hệ 1983–1995", ["NV", "MM"], [], {}, 30, 0.30, True),
    ("cam_g3", "resource", "knowledge_sources", "g3", "Cẩm nang du lịch xã hội cho thế hệ 1996–2008", ["SC", "NV"], [], {}, 30, 0.30, True),
    ("dalat", "place", "geo_places", "dalat_xuanhuong", "Đà Lạt: Hồ Xuân Hương buổi sáng sớm", ["NV", "MM"], [], {}, 7, 0.40, True),
    ("hoian", "place", "geo_places", "hoian_phocotuoi", "Hội An: phố cổ buổi tối, đi bộ cùng nhóm", ["NV", "SC"], [], {}, 7, 0.40, True),
    ("halong", "place", "geo_places", "halong_baitulong", "Hạ Long: một buổi chiều trên vịnh", ["NV", "MM"], [], {}, 7, 0.35, True),
    ("gan_ban", "place", None, None, "Gợi ý điểm dừng gần bạn trong bán kính 5 km", ["NV"],
     [["data_source", "location", "travel_planning"]], {"ban_kinh_km": 5}, 3, 0.35, True),
    ("ky_niem", "practice", None, None, "Ghi lại ba khoảnh khắc đáng nhớ sau mỗi chuyến", ["MM"], [], {}, 14, 0.35, True),
    ("nhom_nho", "practice", None, None, "Một hoạt động nhóm nhỏ: nấu ăn hoặc đi bộ cùng người mới", ["SC"], [], {}, 14, 0.35, True),
    ("nhe_hon", "schedule_adjust", None, None, "Bớt một điểm trong ngày để nhịp đi nhẹ hơn", ["PF"], [], {}, 7, 0.30, True),
    ("hoi_phong_cach", "ask_question", None, None, "Bạn muốn chuyến tới nhẹ nhàng hay có nhiều điều mới?", ["NV", "PF"], [], {}, 30, 0.25, False),
    ("nhac_chuyen", "schedule_adjust", None, None, "Nhắc lịch chuyến đi đã lưu trước một tuần", ["PF"],
     [["interaction", "trip_reminder", "reminders"]], {}, 7, 0.20, True),
    ("tu_van", "human_handoff", None, None, "Chuyển tư vấn viên tour khi chuyến đi lặp lại và lệch nhiều", ["NV", "SC", "PF", "MM"], [],
     {"pd_above": PD_THRESHOLD}, 30, 0.20, False),
    ("khong_lam_gi", "no_action", None, None, "Không gợi ý gì lúc này", [], [], {}, None, 0.05, False),
]


# ---------------- Logic ----------------
def goals_of(u):
    g = GEN[u["gen"]]
    leg = LEGACY.get(u["key"])
    res = {}
    if leg:
        res["legacy"] = dict(id=U(f"goal:{u['key']}:v1"), key=U(f"goalkey:{u['key']}"), ver=1,
                             lo=leg["lo"], hi=leg["hi"], mask=leg["mask"], status="superseded",
                             title=leg["title"], confirmed=P("2025-10-15 10:00"),
                             change="Người dùng muốn đổi sang chuyến đi có trải nghiệm mới", review=None)
        res["active"] = dict(id=U(f"goal:{u['key']}:v2"), key=U(f"goalkey:{u['key']}"), ver=2,
                             lo=g["lo"], hi=g["hi"], mask=g["mask"], status="confirmed", title=g["title"],
                             confirmed=P(leg["confirmed"]), change="Đổi mục tiêu sau khi có trải nghiệm mới",
                             review=P("2027-01-31 00:00"))
    else:
        res["active"] = dict(id=U(f"goal:{u['key']}:v1"), key=U(f"goalkey:{u['key']}"), ver=1,
                             lo=g["lo"], hi=g["hi"], mask=g["mask"], status="confirmed", title=g["title"],
                             confirmed=P("2025-10-15 10:10"), change=None, review=P("2027-01-31 00:00"))
    for gg in res.values():
        assert all(a <= b for a, b in zip(gg["lo"], gg["hi"])), "setpoint lo > hi"
        assert all(0 <= x <= 1 for x in gg["lo"] + gg["hi"]) and all(m > 0 for m in gg["mask"])
    return res


def consents_of(u):
    k = u["key"]
    rows = []

    def add(stype, skey, purpose, status, eff, expires=None, channel="webchat", ref=None):
        rows.append(dict(id=U(f"consent:{k}:{skey}:{eff}"), scope_type=stype, scope_key=skey,
                         purpose=purpose, status=status, effective=P(eff),
                         expires=P(expires) if expires else None, channel=channel,
                         ref=ref or f"ui_action:{k}_{skey}"))

    add("journey", "travel_joy", "travel_planning", "granted", "2025-10-15 09:00", ref=f"ui_action:join_{k}")
    add("data_source", "booking_history", "travel_planning", "granted", "2025-10-15 09:01")
    add("data_source", "chat_text", "travel_planning", "granted", "2025-10-15 09:02")
    if u["loc"]:
        add("data_source", "location", "travel_planning", "granted", "2025-10-15 09:03",
            expires="2027-04-01 00:00", channel="mobile")
    else:
        add("data_source", "location", "travel_planning", "declined", "2025-10-15 09:03", channel="mobile")
    add("interaction", "trip_reminder", "reminders", "granted", "2025-10-15 09:04", channel="zalo")
    if u.get("withdraw"):
        add("interaction", "trip_reminder", "reminders", "withdrawn", "2026-06-10 10:00", channel="zalo")
    return rows


def consent_at(cons, stype, skey, purpose, t):
    cands = [c for c in cons if c["scope_type"] == stype and c["scope_key"] == skey
             and c["purpose"] == purpose and c["effective"] <= t]
    if not cands:
        return None
    c = max(cands, key=lambda c: c["effective"])
    if c["status"] != "granted":
        return c["status"]
    if c["expires"] and c["expires"] <= t:
        return "expired"
    return "granted"


def gaps_for(vals, covs, goal):
    scope = [i for i in range(4) if covs[i] >= COVERAGE_MIN and goal["mask"][i] > 0]
    gaps = [max(0.0, goal["lo"][i] - vals[i], vals[i] - goal["hi"][i]) for i in range(4)]
    return scope, gaps


def tg_of(scope, gaps, goal):
    w = sum(goal["mask"][i] for i in scope)
    return math.sqrt(sum(goal["mask"][i] * gaps[i] ** 2 for i in scope) / w)


def build_user(u):
    k = u["key"]
    goals = goals_of(u)
    cons = consents_of(u)
    cons_by = {(c["scope_type"], c["scope_key"], c["purpose"]): c for c in cons if c["status"] == "granted"}
    journey_id = U(f"consent:{k}:travel_joy:2025-10-15 09:00")
    booking_id = U(f"consent:{k}:booking_history:2025-10-15 09:01")
    chat_id = U(f"consent:{k}:chat_text:2025-10-15 09:02")
    msg_ids = [f"msg_{k}_1", f"msg_{k}_2"]
    gen = GEN[u["gen"]]
    ctx = [
        dict(id=U(f"ctx:{k}:1"), type="availability", value={"ngay_ranh": "cuối tuần"},
             consent=journey_id),
        dict(id=U(f"ctx:{k}:2"), type="budget", value={"currency": "VND", "moi_chuyen": gen["budget"]},
             consent=journey_id),
    ]
    out = dict(goals=goals, cons=cons, ctx=ctx, states=[], evidence=[], snaps=[], decisions=[], outcomes=[],
               messages=[], txns=[])
    last_tg = {}
    prev = None
    for si, (dstr, vals, covs) in enumerate(u["states"]):
        d = D(dstr)
        gk = "legacy" if ("legacy" in goals and si < LEGACY[k]["until"]) else "active"
        goal = goals[gk]
        as_of = P(dstr + " 00:00")
        ev_time = P(f"{(d - dt.timedelta(days=1)).isoformat()} 20:00")
        ev_ids = []
        for di, dim in enumerate(DIMS):
            v, cov = vals[di], covs[di]
            eid = U(f"ev:{k}:{si}:{dim}")
            ev = dict(id=eid, goal=goal["id"], user=k, kind=None, source=None, hash=None, dim=dim,
                      value=v, rubric=None, consent=None, event=ev_time, retracted=None, payload={})
            if cov < COVERAGE_MIN:
                ev.update(kind="model_inference", source="classifier", rubric="travel-rubric-v1",
                          consent=chat_id, payload={"confidence": cov,
                                                    "ghi_chu": "tín hiệu yếu, không dùng để chấm gap"})
            elif dim == "NV":
                ev.update(kind="event", source="activity_log", consent=booking_id,
                          payload={"chuyen_90_ngay": 1 + round(v * 4), "diem_moi": round(v * 6)})
            elif dim == "SC" and si == 2:
                ev.update(kind="self_report", source="chat", hash=msg_ids[1], consent=chat_id,
                          payload={"nguon": "tin nhắn"})
            elif dim == "SC":
                ev.update(kind="self_report", source="survey", consent=chat_id, payload={"nguon": "khảo sát ngắn"})
            elif dim == "PF":
                ev.update(kind="assessment", source="pace_survey", rubric="pace-rubric-v1", consent=journey_id,
                          payload={"diem_moi_ngay": round(v * 6)})
            else:  # MM
                ev.update(kind="self_report", source="travel_journal", consent=chat_id,
                          payload={"khoanh_khac_nho": round(v * 5)})
            if k == "g3_02" and si == 1 and dim == "NV":
                ev["retracted"] = P("2026-06-02 08:00")
            if k == "g3_02" and si == 2 and dim == "NV":
                ev.update(kind="correction", source="travel_journal", hash=None, event=P("2026-06-02 08:00"),
                          payload={"sua_cho": U("ev:g3_02:1:NV"), "ly_do": "ghi trùng một chuyến đi"})
            out["evidence"].append(ev)
            ev_ids.append(eid)
        st = dict(si=si, key=k, d=d, as_of=as_of, computed=P(dstr + " 02:00"), vals=vals, covs=covs,
                  goal=goal, goal_key=gk, ev_ids=ev_ids, id=U(f"state:{k}:{si}"))
        scope, gaps = gaps_for(vals, covs, goal)
        st["scope"], st["gaps"] = scope, gaps
        pd = None
        if prev:
            common = [i for i in scope if i in prev["scope"]]
            if common:
                pd = math.sqrt(sum((vals[i] - prev["vals"][i]) ** 2 for i in common))
        st["pd"] = pd
        tg = tg_of(scope, gaps, goal)
        tv = None
        if goal["id"] in last_tg:
            ptg, pdate = last_tg[goal["id"]]
            tv = (ptg - tg) * 30 / (d - pdate).days
        last_tg[goal["id"]] = (tg, d)
        out["snaps"].append(dict(state=st["id"], goal=goal["id"], dims=[DIMS[i] for i in scope],
                                 tg=tg, pas=1 - tg, tv=tv, pd=pd, per=[gaps[i] for i in scope],
                                 re=False, computed=st["computed"], si=si, user=k))
        if "legacy" in goals and si == 2:
            lg = goals["legacy"]
            lscope, lgaps = gaps_for(vals, covs, lg)
            ltg = tg_of(lscope, lgaps, lg)
            out["snaps"].append(dict(state=st["id"], goal=lg["id"], dims=[DIMS[i] for i in lscope],
                                     tg=ltg, pas=1 - ltg, tv=None, pd=pd, per=[lgaps[i] for i in lscope],
                                     re=True, computed=st["computed"], si=si, user=k))
        out["states"].append(st)
        prev = st
    # chat messages
    for n, (ms, dstr) in enumerate([(u["msgs"][0], u["states"][0][0]), (u["msgs"][1], u["states"][2][0])], start=1):
        created = P(f"{(D(dstr) - dt.timedelta(days=1)).isoformat()} 20:00")
        out["messages"].append(dict(hash=f"msg_{k}_{n}", text=ms, created=created,
                                    channel=u["channel"], touch=(f"tp_{k}" if u["loc"] else None)))
    # giao dịch du lịch (3 giao dịch)
    base_amt = {"flight": 2100000, "hotel": 1450000, "tour": 2800000}
    mult = {"G1": 1.2, "G2": 1.0, "G3": 0.7}[u["gen"]]
    for n, ttype in enumerate(["flight", "hotel", "tour"]):
        st = u["states"][n]
        when = P(f"{(D(st[0]) + dt.timedelta(days=5)).isoformat()} 09:00")
        dest = u.get("city") or DESTS[(n + len(k)) % len(DESTS)]
        out["txns"].append(dict(id=f"txn_{k}_{n + 1}", type=ttype, when=when,
                                amount=round(base_amt[ttype] * mult, -3), dest=dest, pax=2 if n else 1))
    return out


def decide(u, st, cons, ctx_ids, explore=False):
    proposed = dt.datetime.combine(st["d"] + dt.timedelta(days=1), dt.time(8, 0), tzinfo=TZ)
    cands = []
    for code, kind, rtab, rkey, title, dims, req, pre, cd, base, needs_cov in ITEMS:
        reason = None
        for stype, skey, purp in req:
            s = consent_at(cons, stype, skey, purp, proposed)
            if s is None or s in ("declined", "expired"):
                reason = f"missing_consent:{skey}"
                break
            if s == "withdrawn":
                reason = f"consent_withdrawn:{skey}"
                break
        if reason is None and needs_cov:
            low = [dd for dd in dims if st["covs"][DIM_IDX[dd]] < COVERAGE_MIN]
            if low:
                reason = f"low_evidence_coverage_{low[0]}"
        tg_sum = sum(st["gaps"][DIM_IDX[dd]] for dd in dims if DIM_IDX[dd] in st["scope"])
        if reason is None and kind not in ("no_action", "ask_question") and dims and tg_sum == 0:
            reason = "gap_small"
        if reason is None and pre.get("pd_above") is not None:
            if st["pd"] is None:
                reason = "no_drift_baseline"
            elif st["pd"] <= pre["pd_above"]:
                reason = "drift_below_threshold"
        score = 0.05 if kind == "no_action" else round(base + tg_sum, 2)
        cands.append(dict(code=code, kind=kind, rtab=rtab, rkey=rkey, title=title, dims=dims, req=req,
                          pre=pre, cd=cd, score=score, reason=reason))
    eligible = sorted([c for c in cands if c["reason"] is None],
                      key=lambda c: (-c["score"], 0 if c["kind"] == "human_handoff" else 1, c["code"]))
    chosen = eligible[1] if explore else eligible[0]
    assert explore or chosen is eligible[0]
    gl = []
    if chosen["kind"] == "ask_question":
        gr = "ask_first" if any(c < COVERAGE_MIN for c in st["covs"]) else "allowed"
        gd = {"failed": "low_evidence_coverage", "dims": [DIMS[i] for i, c in enumerate(st["covs"]) if c < COVERAGE_MIN]} if gr == "ask_first" else {}
    elif chosen["kind"] == "human_handoff":
        gr, gd = "needs_review", {}
    else:
        gr, gd = "allowed", {}
    executed, check = None, None
    if chosen["kind"] != "no_action":
        executed = proposed + (dt.timedelta(hours=2) if gr == "needs_review" else dt.timedelta(minutes=5))
        check = {"consent_ok": True, "checked_at": executed.isoformat(), "goal_status": "confirmed",
                 "state_age_hours": round((proposed - st["as_of"]).total_seconds() / 3600, 1)}
        if gr == "needs_review":
            check["reviewer"] = "tu_van_vien_travel"
    return dict(id=U(f"dec:{st['key']}:{st['si']}"), user=st["key"], state=st["id"], goal=st["goal"]["id"],
                ctx=ctx_ids, cands=cands, chosen=chosen, guard=gr, guard_detail=gl or gd,
                proposed=proposed, executed=executed, check=check, explore=explore,
                prop=0.10 if explore else 0.90, arm="explore_eps_0.1" if explore else "greedy_v1",
                touch=(f"tp_{st['key']}" if st["key"] in LOC_USERS else None), st_obj=st)


def outcomes_for(dec, u):
    res = []
    if dec["executed"] is None:
        return res
    ex = dec["executed"]
    res.append(dict(dec=dec["id"], type="delivered", at=ex, rating=None, detail={}))
    kind = dec["chosen"]["kind"]
    if kind == "ask_question":
        res.append(dict(dec=dec["id"], type="accepted", at=ex + dt.timedelta(days=1), rating=4,
                        detail={"tra_loi": "Muốn nhẹ nhàng, có thêm một điều mới nhỏ"}))
    elif kind == "human_handoff":
        res.append(dict(dec=dec["id"], type="accepted", at=ex + dt.timedelta(hours=3), rating=4,
                        detail={"ghi_chu": "tư vấn viên đã gọi hỏi thăm"}))
    else:
        res.append(dict(dec=dec["id"], type="opened", at=ex + dt.timedelta(minutes=30), rating=None, detail={}))
        if (len(u["key"]) + dec["st_obj"]["si"]) % 2 == 0:
            res.append(dict(dec=dec["id"], type="completed", at=ex + dt.timedelta(days=2), rating=5,
                            detail={"ghi_chu": "đã thử gợi ý"}))
        else:
            res.append(dict(dec=dec["id"], type="accepted", at=ex + dt.timedelta(days=1), rating=4, detail={}))
    if u.get("harm_at") == dec["st_obj"]["si"]:
        res.append(dict(dec=dec["id"], type="harm_report", at=ex + dt.timedelta(days=2), rating=None,
                        detail={"nhom": "qua_tai", "ghi_chu": "lịch trình quá dày, muốn ít điểm hơn",
                                "hanh_dong": "xem_lai_policy"}))
    return res


LOC_USERS = {u["key"] for u in USERS if u["loc"]}


def main(path):
    built = [build_user(u) for u in USERS]

    # ---- kiểm tra bất biến ----
    for u, b in zip(USERS, built):
        birth = D(u["birth"])
        age = age_on(birth, TODAY)
        assert age >= 18, f"{u['key']} dưới 18 tuổi"
        ev_by_id = {e["id"]: e for e in b["evidence"]}
        for st in b["states"]:
            for eid in st["ev_ids"]:
                e = ev_by_id[eid]
                assert e["event"] <= st["as_of"], f"{u['key']} bằng chứng sau as_of"
                if e["retracted"]:
                    assert e["retracted"] > st["as_of"] or True
        if u["key"] == "g3_02":
            s2 = b["states"][2]
            assert U("ev:g3_02:1:NV") not in s2["ev_ids"], "bằng chứng đã thu hồi còn trong state mới"

    # ---- quyết định & kết quả ----
    all_dec, all_out, all_items_ok = [], [], True
    for u, b in zip(USERS, built):
        ctx_ids = [c["id"] for c in b["ctx"]]
        for si in (1, 2):
            st = b["states"][si]
            explore = (u.get("explore") == si)
            dec = decide(u, st, b["cons"], ctx_ids, explore=explore)
            # tiêu chí: lựa chọn không vi phạm đồng ý tại thời điểm đề xuất
            ch = dec["chosen"]
            for stype, skey, purp in ch["req"]:
                assert consent_at(b["cons"], stype, skey, purp, dec["proposed"]) == "granted"
            all_dec.append((u, dec))
            all_out.extend(outcomes_for(dec, u))
    harm_ok = any(o["type"] == "harm_report" for o in all_out)

    # ---- sinh SQL ----
    S = []
    S.append(f"""-- ============================================================================
-- SEED TOÀN BỘ BẢNG SQL | tenant = '{TENANT}' | lĩnh vực: DU LỊCH
-- Persona: từ ít trải nghiệm mới, lịch trình lặp lại -> vui hơn, nhiều kỷ niệm
-- Thế hệ: 1970–1982 | 1983–1995 | 1996–2008 (9 người, 3 người mỗi thế hệ)
--
-- CHÚ Ý
--  * Toàn bộ dữ liệu là TỔNG HỢP. Tên, email, số điện thoại không phải người thật.
--  * Mọi người dùng đều từ 18 tuổi trở lên tại 12/10/2026 (kiểm tra bằng ngày sinh).
--  * Không lưu trạng thái cảm xúc, sức khỏe, tôn giáo hay chẩn đoán. Chỉ lưu hành vi.
--  * Embedding là vector giả (hàm seed_vec768), chỉ để kiểm thử truy vấn, không có
--    ý nghĩa ngữ nghĩa. Hàm này bị xóa ở cuối file.
--  * Tọa độ địa điểm và thời tiết là gần đúng, chỉ dùng để thử nghiệm.
--  * customer_metrics được tính bằng refresh_customer_metrics(), nên giá trị phụ
--    thuộc ngày chạy (cửa sổ 90 ngày tính từ NOW()).
--
-- YÊU CẦU: đã cài schema đầy đủ, DB sạch hoặc chưa có tenant '{TENANT}'.
-- Chạy:  psql -d leo_bot -f travel_seed_all_tables.sql
-- ============================================================================

BEGIN;

-- Hàm tiện ích tạm: vector 768 chiều giả, xác định theo chuỗi đầu vào
CREATE OR REPLACE FUNCTION seed_vec768(seed TEXT) RETURNS vector(768)
LANGUAGE sql IMMUTABLE AS $$
    SELECT array_agg(
        ((((hashtext(seed || ':' || i::text) % 2000) + 2000) % 2000) / 1000.0 - 1.0)::real
        ORDER BY i)::vector(768)
    FROM generate_series(1, 768) AS i;
$$;
""")

    # 1. Cấu hình tenant
    S.append("-- 1. tenant_metrics_config (tham số CLV theo VND)\n" + ins(
        "tenant_metrics_config", ["tenant_id", "expected_lifetime_years", "cac", "clv_happy_threshold"],
        [[q(TENANT), "2.5", "500000", "5000000"]]))

    # 2. Hồ sơ khách hàng
    rows = []
    for idx, (u, b) in enumerate(zip(USERS, built), start=1):
        k = u["key"]
        birth = D(u["birth"])
        meta = {"the_he": GEN[u["gen"]]["cohort"], "ngay_sinh": u["birth"], "tong_hop": True}
        rows.append([q(TENANT), q(f"cdp_{k}"), q(u["name"]), q(f"{k}@example.com"),
                     q(f"+8490000{idx:04d}"), q("VN"), str(age_on(birth, TODAY)), "NULL", jb(meta),
                     vec(f"profile:{k}"), ts(P("2025-10-15 09:00")), ts(P("2025-10-15 09:00"))])
    S.append("-- 2. customer_profile\n" + ins(
        "customer_profile", ["tenant_id", "cdp_profile_id", "full_name", "email", "phone", "country", "age",
                             "gender", "metadata", "profile_embedding", "created_at", "updated_at"], rows))

    # 3. Giao dịch du lịch
    rows = []
    for u, b in zip(USERS, built):
        for t in b["txns"]:
            rows.append([q(TENANT), q(f"tv_{u['key']}"), q(t["id"]), q(f"cdp_{u['key']}"),
                         q("booking_seed"), q(t["type"]), q("completed"), ts(t["when"]),
                         nn(float(t["amount"])), q("VND"),
                         jb({"diem_den": t["dest"], "so_khach": t["pax"], "loai": t["type"]}),
                         vec(f"txn:{t['id']}"), q("du lịch"), q("đặt chuyến đi"), "0.9",
                         ts(t["when"]), ts(t["when"]), q("system")])
    S.append("-- 3. transactional_context (giao dịch đặt chuyến)\n" + ins(
        "transactional_context", ["tenant_id", "user_id", "txn_id", "cdp_profile_id", "source_system", "txn_type",
                                  "txn_status", "txn_timestamp", "amount", "currency", "context_data", "embedding",
                                  "category_label", "intent_label", "intent_confidence", "created_at",
                                  "updated_at", "updated_by"], rows))

    S.append("-- 4. customer_metrics: tính bằng hàm có sẵn của schema\n"
             f"SELECT refresh_customer_metrics({q(TENANT)});\n")

    # 5. Tin nhắn chat + embedding
    rows, erows = [], []
    for u, b in zip(USERS, built):
        for m in b["messages"]:
            rows.append([q(TENANT), q(m["hash"]), q(f"tv_{u['key']}"), q(f"cdp_{u['key']}"),
                         q("persona_travel_joy_v1"), (q(m["touch"]) if m["touch"] else "NULL"),
                         q(m["channel"]), q("active"), q("user"), q(m["text"]),
                         txa(["du lịch", "lịch trình"]), ts(m["created"]), q("travel_planning"), "0.8",
                         ts(m["created"])])
            erows.append([q(TENANT), q(m["hash"]), vec(f"msg:{m['hash']}"), ts(m["created"])])
    S.append("-- 5a. chat_messages\n" + ins(
        "chat_messages", ["tenant_id", "message_hash", "user_id", "cdp_profile_id", "persona_id", "touchpoint_id",
                          "channel", "status", "role", "message", "keywords", "created_at",
                          "last_intent_label", "last_intent_confidence", "last_updated"], rows))
    S.append("-- 5b. chat_message_embeddings\n" + ins(
        "chat_message_embeddings", ["tenant_id", "message_hash", "embedding", "created_at"], erows))

    # 6. Điểm chạm vị trí (chỉ người đã đồng ý)
    rows = []
    for u in USERS:
        if not u["loc"]:
            continue
        lat, lng = u["ll"]
        k = u["key"]
        rows.append([q(TENANT), q(f"tp_{k}"), q(f"tv_{k}"), str(lat), str(lng),
                     f"ST_SetSRID(ST_MakePoint({lng},{lat}),4326)",
                     q(f"{u['city']} — điểm ghé gần nhất"), q("Dữ liệu tổng hợp, không phải vị trí thật"),
                     q("destination"), txa(["du lịch"]), vec(f"tp:{k}"), jb({"tong_hop": True}),
                     ts(P("2026-08-01 10:00")), ts(P("2026-08-01 10:00")), ts(P("2026-08-01 10:00"))])
    S.append("-- 6. touchpoints (chỉ người đã bật đồng ý vị trí)\n" + ins(
        "touchpoints", ["tenant_id", "touchpoint_id", "user_id", "latitude", "longitude", "geom", "name",
                        "description", "type", "keywords", "embedding", "metadata", "created_at", "updated_at",
                        "last_seen_at"], rows))

    # 7. Ngữ cảnh hội thoại (một dòng mỗi người)
    rows = []
    for u in USERS:
        k = u["key"]
        tp = f"tp_{k}" if u["loc"] else f"conv_{k}"
        rows.append([q(TENANT), q(f"tv_{k}"), q(tp), q(f"cdp_{k}"),
                     jb({"chu_de": "lập kế hoạch chuyến đi", "dia_diem_gan_nhat": u.get("city")}),
                     vec(f"conv:{k}"), q("travel_planning"), "0.8", q("system"),
                     ts(P("2026-09-01 10:00")), ts(P("2026-09-01 10:00"))])
    S.append("-- 7. conversational_context\n" + ins(
        "conversational_context", ["tenant_id", "user_id", "touchpoint_id", "cdp_profile_id", "context_data",
                                   "embedding", "intent_label", "intent_confidence", "updated_by", "created_at",
                                   "updated_at"], rows))

    # 8. Tri thức (knowledge_sources + knowledge_chunks)
    ks_rows, kc_rows = [], []
    for key, name, chunks in KNOWLEDGE:
        ks_rows.append([q(U(f"ks:{key}")), q(TENANT), q("system"), q("knowledge_base_article"), q(name),
                        q(key), "NULL", q("active"), jb({"lang": "vi", "nguon": "nội dung biên tập tổng hợp"}),
                        ts(P("2026-01-10 09:00")), ts(P("2026-01-10 09:00"))])
        for n, text in enumerate(chunks, start=1):
            kc_rows.append([q(U(f"kc:{key}:{n}")), q(TENANT), q(U(f"ks:{key}")), q(text), vec(f"kc:{key}:{n}"),
                            str(n), jb({"muc": n}), ts(P("2026-01-10 09:00"))])
    S.append("-- 8a. knowledge_sources\n" + ins(
        "knowledge_sources", ["id", "tenant_id", "user_id", "source_type", "name", "code_name", "uri", "status",
                              "metadata", "created_at", "updated_at"], ks_rows))
    S.append("-- 8b. knowledge_chunks\n" + ins(
        "knowledge_chunks", ["id", "tenant_id", "source_id", "content", "embedding", "chunk_sequence", "metadata",
                             "created_at"], kc_rows))

    # 9. Địa điểm dùng chung (tenant 'global') và thời tiết
    rows = []
    for slug, name, prov, region, lat, lng, rating, cnt, desc, tags in GEO:
        rows.append([q(U(f"geo:{slug}")), q("global"), q(f"gplaces:tv_{slug}"), q(name), q("Attraction"),
                     txa(tags), q(f"{name}, {prov}"), q(region), str(lat), str(lng),
                     f"ST_SetSRID(ST_MakePoint({lng},{lat}),4326)", str(rating), str(cnt), q(desc),
                     ts(P("2026-03-01 09:00")), ts(P("2026-03-01 09:00"))])
    S.append("-- 9a. geo_places (tenant global)\n" + ins(
        "geo_places", ["id", "tenant_id", "geo_place_id", "name", "category", "tags", "address", "region_id",
                       "latitude", "longitude", "geom", "rating", "rating_count", "description", "created_at",
                       "updated_at"], rows, tail="\nON CONFLICT DO NOTHING;"))
    rows = []
    for name, city, lat, lng, mn, mx, rain in WEATHER:
        rows.append([q(U(f"wx:{city}")), q("global"),
                     jb({"nguon": "du_lieu_mau_tong_hop", "ghi_chu": "Không phải dữ liệu thời tiết thật",
                         "ngay": "2026-10-12", "nhiet_do_c": {"min": mn, "max": mx}, "xac_suat_mua_pct": rain}),
                     q(name), q(city), q("VN"), q("Asia/Ho_Chi_Minh"), str(lat), str(lng),
                     f"ST_SetSRID(ST_MakePoint({lng},{lat}),4326)::geography", vec(f"wx:{city}")])
    S.append("-- 9b. weather_data (cache tổng hợp, tenant global)\n" + ins(
        "weather_data", ["id", "tenant_id", "original_data", "location_name", "city", "country", "time_zone",
                         "latitude", "longitude", "geog", "weather_embedding"], rows))

    # 10. Người dùng nội bộ và page_index
    rows = []
    for email, login, name, role in [
        ("admin.travel@example.com", "quan_tri_seed", "Quản trị nội dung (seed)", 1),
        ("content.travel@example.com", "bien_tap_seed", "Biên tập nội dung (seed)", 2),
        ("support.travel@example.com", "ho_tro_seed", "Hỗ trợ khách (seed)", 3),
    ]:
        rows.append([q(TENANT), "NULL", "NULL", str(int(P("2026-01-05 09:00").timestamp() * 1000)),
                     jb({"seed": True}), q(name), "FALSE", "NULL", "0", str(role), "1",
                     q(email), q(login), q("SEED_NOT_A_REAL_PASSWORD"), txa(["travel:read"]), "NULL",
                     txa(["travel"]), q("Du lịch"), ts(P("2026-01-05 09:00")), ts(P("2026-01-05 09:00"))])
    cols_su = ["tenant_id", "activation_key", "avatar_url", "creation_time", "custom_data", "display_name",
               "is_online", "modification_time", "registered_time", "role", "status", "user_email", "user_login",
               "user_pass", "access_profile_fields", "action_logs", "in_groups", "business_unit", "created_at",
               "updated_at"]
    S.append("-- 10a. system_users (mật khẩu là chuỗi giả, KHÔNG phải băm thật)\n" + ins(
        "system_users", cols_su, rows))
    rows = []
    for pno, title in [(1, "Du lịch chậm"), (2, "Trải nghiệm mới"), (3, "Đi cùng bạn bè")]:
        rows.append([q(TENANT), str(pno), jb([{"chuong": title, "trang": pno}]), vec(f"page:{pno}")])
    S.append("-- 10b. page_index\n" + ins("page_index", ["tenant_id", "page_number", "toc", "embedding"], rows))

    # 11. Persona: schema
    dims_json = [
        {"idx": 0, "code": "NV", "name": "novelty", "definition": "Số trải nghiệm mới trong 90 ngày (điểm, món, hoạt động)",
         "unit": "0..1", "normalization": "chuyến và điểm mới quy về 0..1", "direction": "higher_is_closer",
         "requires_consent_scope": "data_source:booking_history"},
        {"idx": 1, "code": "SC", "name": "social", "definition": "Kết nối có ý nghĩa với người đồng hành",
         "unit": "0..1", "normalization": "khảo sát hoặc tin nhắn, kẹp 0..1", "direction": "higher_is_closer",
         "requires_consent_scope": "data_source:chat_text"},
        {"idx": 2, "code": "PF", "name": "pace_fit", "definition": "Mức phù hợp nhịp độ (số điểm mỗi ngày)",
         "unit": "0..1", "normalization": "điểm mỗi ngày / 6, kẹp 0..1", "direction": "in_range_is_best",
         "requires_consent_scope": "journey:travel_joy"},
        {"idx": 3, "code": "MM", "name": "memorable", "definition": "Mức ghi nhận khoảnh khắc đáng nhớ sau chuyến đi",
         "unit": "0..1", "normalization": "khoảnh khắc ghi lại / 5, kẹp 0..1", "direction": "higher_is_closer",
         "requires_consent_scope": "data_source:chat_text"},
    ]
    S.append("-- 11. persona_schemas (từ điển dữ liệu, lĩnh vực travel)\n" + ins(
        "persona_schemas", ["id", "tenant_id", "domain", "version", "status", "dimensions", "distance_config", "notes"],
        [[q(U("schema:travel:v1")), q(TENANT), q("travel"), "1", q("active"), jb(dims_json),
          jb({"metric": "weighted_euclidean_to_range", "weights_from": "goal.dim_mask", "d_max": 1.0}),
          q("Persona du lịch: từ nhàm chán sang vui hơn. Chiều PF là khoảng mục tiêu, quá dày và quá thưa đều lệch.")]]))

    # 12. Đồng ý
    rows = []
    for u, b in zip(USERS, built):
        for c in b["cons"]:
            rows.append([q(c["id"]), q(TENANT), q(f"tv_{u['key']}"), q(f"cdp_{u['key']}"), q(c["scope_type"]),
                         q(c["scope_key"]), q(c["purpose"]), q(c["channel"]), q(c["status"]), q("v2026.1"),
                         ts(c["effective"]), ts(c["expires"]), q(c["ref"])])
    S.append("-- 12. persona_consents (sổ chỉ thêm; rút đồng ý = dòng mới)\n" + ins(
        "persona_consents", ["id", "tenant_id", "user_id", "cdp_profile_id", "scope_type", "scope_key", "purpose",
                             "channel", "status", "notice_version", "effective_at", "expires_at", "evidence_ref"],
        rows))

    # 13. Mục tiêu
    rows = []
    for u, b in zip(USERS, built):
        g = GEN[u["gen"]]
        for gk, gg in b["goals"].items():
            rows.append([q(gg["id"]), q(TENANT), q(gg["key"]), str(gg["ver"]),
                         q(f"tv_{u['key']}"), q(f"cdp_{u['key']}"), q(U("schema:travel:v1")), q(gg["title"]),
                         q(u["words"]),
                         jb({"NV": "số trải nghiệm mới trong 90 ngày", "SC": "khảo sát và tin nhắn",
                             "PF": "khảo sát nhịp độ", "MM": "nhật ký chuyến đi"}),
                         jb(g["bound"]),
                         rla(gg["lo"]), rla(gg["hi"]), rla(gg["mask"]), q(gg["status"]),
                         (q(gg["change"]) if gg["change"] else "NULL"),
                         ts(gg["confirmed"]), ts(gg["review"])])
    S.append("-- 13. persona_goals (phiên bản mục tiêu; đổi mục tiêu = dòng mới)\n" + ins(
        "persona_goals", ["id", "tenant_id", "goal_key", "version", "user_id", "cdp_profile_id", "schema_id", "title",
                          "participant_words", "evidence_criteria", "boundaries", "setpoint_min", "setpoint_max",
                          "dim_mask", "status", "change_reason", "participant_confirmed_at", "review_at"], rows))

    # 14. Bằng chứng
    rows = []
    for u, b in zip(USERS, built):
        for e in b["evidence"]:
            hash_ = q(e["hash"]) if e["hash"] else "NULL"
            cons_ids = {"booking": None}
            rows.append([q(e["id"]), q(TENANT), q(f"tv_{u['key']}"), q(e["goal"]), q(e["kind"]), q(e["source"]),
                         hash_, "NULL", q(e["dim"]), repr(round(float(e["value"]), 4)),
                         (q(e["rubric"]) if e["rubric"] else "NULL"), "NULL", q(e["consent"]), "NULL",
                         ts(e["event"]), "NULL", ts(e["retracted"]), jb(e["payload"])])
    S.append("-- 14. persona_evidence (nguồn gốc; bằng chứng thu hồi giữ dòng và có retracted_at)\n" + ins(
        "persona_evidence", ["id", "tenant_id", "user_id", "goal_id", "kind", "source", "source_message_hash",
                             "source_txn_id", "dimension_code", "observed_value", "rubric_version", "assessor",
                             "consent_id", "missing_reason", "event_time", "valid_until", "retracted_at", "payload"],
        rows))

    # 15. Trạng thái
    rows = []
    for u, b in zip(USERS, built):
        for st in b["states"]:
            rows.append([q(st["id"]), q(TENANT), q(f"tv_{u['key']}"), q(f"cdp_{u['key']}"), q(st["goal"]["id"]),
                         q(U("schema:travel:v1")), q(MODEL_VERSION), rla(st["vals"]),
                         rla([round(0.01 + 0.08 * (1 - c), 4) for c in st["covs"]]),
                         rla(st["covs"]), uua(st["ev_ids"]), vec(f"state:{st['id']}"),
                         ts(st["as_of"]), ts(st["computed"])])
    S.append("-- 15. persona_states (ước lượng theo thời gian; persona_embedding chỉ để truy xuất)\n" + ins(
        "persona_states", ["id", "tenant_id", "user_id", "cdp_profile_id", "goal_id", "schema_id", "model_version",
                           "mean", "variance", "evidence_coverage", "evidence_ids", "persona_embedding", "as_of",
                           "computed_at"], rows))

    # 16. Khoảng cách (dẫn xuất)
    rows = []
    for u, b in zip(USERS, built):
        for sn in b["snaps"]:
            rows.append([q(TENANT), q(sn["state"]), q(sn["goal"]), q(DIST_VERSION), txa(sn["dims"]),
                         repr(round(sn["tg"], 4)), repr(round(sn["pas"], 4)),
                         ("NULL" if sn["tv"] is None else repr(round(sn["tv"], 4))),
                         ("NULL" if sn["pd"] is None else repr(round(sn["pd"], 4))),
                         rla(sn["per"]), nn(sn["re"]), ts(sn["computed"])])
    S.append("-- 16. persona_gap_snapshots (TG, PAS, TV, PD; tính lại được từ states và goals)\n" + ins(
        "persona_gap_snapshots", ["tenant_id", "state_id", "goal_id", "distance_version", "dims_in_scope", "tg",
                                  "pas", "tv", "pd", "per_dim_gap", "is_reanalysis", "computed_at"], rows))

    # 17. Ngữ cảnh
    rows = []
    for u, b in zip(USERS, built):
        for c in b["ctx"]:
            rows.append([q(c["id"]), q(TENANT), q(f"tv_{u['key']}"), "NULL", q(c["type"]), jb(c["value"]),
                         q("self_report"), q(c["consent"]), ts(P("2026-01-01 00:00")), ts(P("2026-12-31 23:59"))])
    S.append("-- 17. persona_contexts (hoàn cảnh, không phải danh tính; luôn có hạn)\n" + ins(
        "persona_contexts", ["id", "tenant_id", "user_id", "touchpoint_id", "context_type", "value", "source",
                             "consent_id", "valid_from", "valid_until"], rows))

    # 18. Gợi ý: danh mục mục
    rows = []
    for code, kind, rtab, rkey, title, dims, req, pre, cd, base, needs_cov in ITEMS:
        ref_id = "NULL"
        if rkey is not None:
            ref_id = q(U(f"ks:{rkey}")) if rtab == "knowledge_sources" else q(U(f"geo:{rkey}"))
        rows.append([q(U(f"item:{code}")), q(TENANT), q(kind), (q(rtab) if rtab else "NULL"), ref_id, q(title),
                     txa(dims), jb([{"scope_type": s[0], "scope_key": s[1], "purpose": s[2]} for s in req]),
                     jb(pre), (f"INTERVAL '{cd} days'" if cd else "NULL"), vec(f"item:{code}"), "TRUE",
                     ts(P("2026-01-10 09:00")), ts(P("2026-01-10 09:00"))])
    S.append("-- 18. recommendation_items (danh mục ứng viên)\n" + ins(
        "recommendation_items", ["id", "tenant_id", "action_kind", "ref_table", "ref_id", "title", "target_dims",
                                 "required_consents", "preconditions", "cooldown", "embedding", "is_active",
                                 "created_at", "updated_at"], rows))

    # 19. Quyết định
    rows = []
    for u, dec in all_dec:
        ch = dec["chosen"]
        cand_json = [{"item_id": U(f"item:{c['code']}"), "score": c["score"], "excluded_by": c["reason"]}
                     for c in dec["cands"]]
        rows.append([q(dec["id"]), q(TENANT), q(f"tv_{dec['user']}"), (q(dec["touch"]) if dec["touch"] else "NULL"),
                     q(dec["state"]), q(dec["goal"]), uua(dec["ctx"]), q(POLICY), jb(cand_json),
                     q(U(f"item:{ch['code']}")), q(ch["kind"]), repr(dec["prop"]), nn(dec["explore"]),
                     q(dec["arm"]), q(dec["guard"]), jb(dec["guard_detail"]), ts(dec["proposed"]),
                     ts(dec["executed"]), (jb(dec["check"]) if dec["check"] else "NULL")])
    S.append("-- 19. recommendation_decisions (vì sao bot hành động, hoặc chọn không làm gì)\n" + ins(
        "recommendation_decisions", ["id", "tenant_id", "user_id", "touchpoint_id", "state_id", "goal_id",
                                     "context_ids", "policy_version", "candidates", "chosen_item_id", "chosen_kind",
                                     "propensity", "is_exploration", "experiment_arm", "guardrail_result",
                                     "guardrail_detail", "proposed_at", "executed_at", "execution_check"], rows))

    # 20. Phản hồi
    rows = []
    for o in all_out:
        rows.append([q(TENANT), q(o["dec"]), q(o["type"]), ts(o["at"]),
                     (str(o["rating"]) if o["rating"] else "NULL"), jb(o["detail"])])
    S.append("-- 20. recommendation_outcomes (phản hồi, gồm báo cáo gây hại)\n" + ins(
        "recommendation_outcomes", ["tenant_id", "decision_id", "event_type", "occurred_at", "participant_rating",
                                    "detail"], rows))

    S.append("-- Dọn hàm tạm\nDROP FUNCTION seed_vec768(TEXT);\n\nCOMMIT;\n")

    S.append("""
-- ============================================================================
-- KIỂM TRA SAU KHI NẠP
-- ============================================================================
-- Số dòng từng bảng (tenant leo_travel)
SELECT 'customer_profile' AS bang, count(*) FROM customer_profile WHERE tenant_id='leo_travel'
UNION ALL SELECT 'transactional_context', count(*) FROM transactional_context WHERE tenant_id='leo_travel'
UNION ALL SELECT 'customer_metrics', count(*) FROM customer_metrics WHERE tenant_id='leo_travel'
UNION ALL SELECT 'chat_messages', count(*) FROM chat_messages WHERE tenant_id='leo_travel'
UNION ALL SELECT 'chat_message_embeddings', count(*) FROM chat_message_embeddings WHERE tenant_id='leo_travel'
UNION ALL SELECT 'conversational_context', count(*) FROM conversational_context WHERE tenant_id='leo_travel'
UNION ALL SELECT 'touchpoints', count(*) FROM touchpoints WHERE tenant_id='leo_travel'
UNION ALL SELECT 'knowledge_sources', count(*) FROM knowledge_sources WHERE tenant_id='leo_travel'
UNION ALL SELECT 'knowledge_chunks', count(*) FROM knowledge_chunks WHERE tenant_id='leo_travel'
UNION ALL SELECT 'system_users', count(*) FROM system_users WHERE tenant_id='leo_travel'
UNION ALL SELECT 'page_index', count(*) FROM page_index WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_schemas', count(*) FROM persona_schemas WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_consents', count(*) FROM persona_consents WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_goals', count(*) FROM persona_goals WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_evidence', count(*) FROM persona_evidence WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_states', count(*) FROM persona_states WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_gap_snapshots', count(*) FROM persona_gap_snapshots WHERE tenant_id='leo_travel'
UNION ALL SELECT 'persona_contexts', count(*) FROM persona_contexts WHERE tenant_id='leo_travel'
UNION ALL SELECT 'recommendation_items', count(*) FROM recommendation_items WHERE tenant_id='leo_travel'
UNION ALL SELECT 'recommendation_decisions', count(*) FROM recommendation_decisions WHERE tenant_id='leo_travel'
UNION ALL SELECT 'recommendation_outcomes', count(*) FROM recommendation_outcomes WHERE tenant_id='leo_travel';

-- Xu hướng TG theo thế hệ: nhàm chán (bước 1) -> vui hơn (bước 3)
WITH buoc AS (
    SELECT user_id, id AS state_id, row_number() OVER (PARTITION BY user_id ORDER BY as_of) AS buoc
    FROM persona_states WHERE tenant_id='leo_travel')
SELECT cp.metadata->>'the_he' AS the_he, b.buoc, round(avg(g.tg)::numeric, 4) AS tg_tb, count(*) AS so_nguoi
FROM buoc b
JOIN persona_gap_snapshots g ON g.tenant_id='leo_travel' AND g.state_id=b.state_id AND NOT g.is_reanalysis
JOIN customer_profile cp ON cp.tenant_id='leo_travel' AND cp.cdp_profile_id = replace(b.user_id,'tv_','cdp_')
GROUP BY 1,2 ORDER BY 1,2;

-- Không có bằng chứng sau thời điểm của state (kỳ vọng: 0 dòng)
SELECT s.id, e.id FROM persona_states s JOIN persona_evidence e
  ON e.tenant_id=s.tenant_id AND e.id = ANY(s.evidence_ids)
WHERE s.tenant_id='leo_travel' AND e.event_time > s.as_of;

-- Không có quyết định chọn mục khi đồng ý không còn hiệu lực (kỳ vọng: 0 dòng)
SELECT d.id FROM recommendation_decisions d
JOIN recommendation_items i ON i.tenant_id=d.tenant_id AND i.id=d.chosen_item_id
WHERE d.tenant_id='leo_travel' AND i.required_consents <> '[]'::jsonb
  AND d.executed_at IS NOT NULL AND NOT (d.execution_check->>'consent_ok')::boolean;
""")

    text = "\n".join(S)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    # ---- báo cáo ----
    print(f"Đã ghi {path}", file=sys.stderr)
    print(f"persona_gap_snapshots: {sum(len(b['snaps']) for b in built)} dòng", file=sys.stderr)
    print(f"recommendation_decisions: {len(all_dec)}; outcomes: {len(all_out)}; harm_report: {harm_ok}",
          file=sys.stderr)
    for gen in ["G1", "G2", "G3"]:
        row = []
        for si in range(3):
            vals = []
            for u, b in zip(USERS, built):
                if u["gen"] != gen:
                    continue
                for sn in b["snaps"]:
                    if sn["user"] == u["key"] and sn["si"] == si and not sn["re"]:
                        vals.append(sn["tg"])
            row.append(round(sum(vals) / len(vals), 4) if vals else None)
        print(f"{gen} {GEN[gen]['cohort']}: TG bước 1/2/3 = {row}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "travel_seed_all_tables.sql")
