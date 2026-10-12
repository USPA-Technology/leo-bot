# DAG geo marketing cho coffee shop, O2O retail

[`causal_geo_marketing_dag.py`](./causal_geo_marketing_dag.py) định nghĩa duy
nhất job **`geo_marketing_sales_dag`**: mô phỏng chiến dịch location-based
marketing của một cửa hàng, từ vùng phục vụ (catchment) đến online order,
lượt đến cửa hàng và hiệu quả kinh tế O2O (online-to-offline).

Job này độc lập với ví dụ funnel website đơn giản
[`causal_sales_dag`](./causal_sales_dag.md): mỗi module sở hữu config, op,
job và `defs` riêng, không import mô hình của nhau. Package Dagster đăng ký
cả hai job qua [`__init__.py`](./__init__.py), không tạo cạnh giữa chúng.

Đây là mô hình giả định để học và lập kế hoạch, không phải pipeline đo
lường hiệu quả thực tế. Job không đọc GPS, PostGIS, quảng cáo hay POS, và
không gửi thông điệp marketing. Cấu hình mô tả một cửa hàng trong **cùng một
kỳ phân tích** (ví dụ một tuần); chi tiêu, tần suất, walk-in và công suất
phải cùng kỳ. Job geo dùng dữ liệu audience tổng hợp, không theo dõi cá nhân.

## Chọn kịch bản sử dụng

| Kịch bản | Cấu hình quan trọng | Cách diễn giải |
| --- | --- | --- |
| Coffee shop | `radius_km`, `store_visit_rate`, `store_basket_usd`, `purchase_capacity` | Quảng cáo địa phương dẫn đến lượt ghé quán và giao dịch; công suất có thể giới hạn nhu cầu mới |
| O2O retail | `online_order_share`, hai giá trị basket, `gross_margin` | So sánh nhánh mua online với nhánh xem online rồi mua tại cửa hàng |
| Location-based marketing | mật độ audience, `eligible_fraction`, `frequency_cap`, `local_delivery_fraction`, CPM | Kiểm tra ngân sách có vượt lượng hiển thị địa phương có thể tiếp cận hay không |

`online_order_share` phân chia **session có ý định mua**, không phải tỷ lệ
chuyển đổi mua hàng. Online order được giả định phục vụ bằng hệ thống riêng
(ví dụ giao hàng); không tiêu thụ `purchase_capacity` tại cửa hàng. Nếu có
click-and-collect hoặc bếp chung cho giao hàng và khách tại quán, cần mô hình
công suất chung trước khi áp dụng kết quả.

## Job geo marketing: đồ thị và đơn vị

```text
marketing_spend -> geo_ad_impressions -> website_visits -> o2o_journey
seasonality_index ---------------------> website_visits
o2o_journey.online_visits -> online_purchases -----------> campaign_economics
o2o_journey.store_visits  -> store_purchases ------------> campaign_economics
seasonality_index -------> online_purchases, store_purchases
product_quality_index --> online_purchases, store_purchases
marketing_spend ----------------------------------------> campaign_economics
```

`online_purchases` là op riêng của module geo, với phương trình chuyển đổi
online được giữ nguyên. Dagster tạo cạnh từ các output truyền vào op; hai
output của `o2o_journey` là hai nhánh khác nhau, không phải hai bản sao cùng
funnel.

Các op định nghĩa riêng `geo_marketing_spend`, `geo_seasonality_index`,
`geo_product_quality_index` và `geo_website_visits` dùng alias tương ứng
`marketing_spend`, `seasonality_index`, `product_quality_index` và
`website_visits` trong job. Tên định nghĩa khác nhau tránh xung đột khi
Dagster nạp cả hai module; alias giữ nguyên các khóa YAML, output và tên
bước trong lần chạy hiện có. Tên job vẫn là `geo_marketing_sales_dag`.

Spend tại op đầu vào dùng **nghìn USD**. Impressions, website sessions,
online-order sessions, campaign store visits và online purchases dùng
**nghìn**. Output `store_purchases` và các khóa `*_count` của
`campaign_economics` dùng **số giao dịch**, còn `*_usd` dùng **USD**.
Các số lẻ là kỳ vọng mô phỏng, không phải số người hay giao dịch đã quan sát.

### Cấu hình geo mặc định

```yaml
ops:
  marketing_spend:
    config:
      thousands_usd: 10
  seasonality_index:
    config:
      index: 0.5
  product_quality_index:
    config:
      index: 0.7
  geo_ad_impressions:
    config:
      radius_km: 1
      audience_per_square_km: 5000
      eligible_fraction: 0.6
      frequency_cap: 3
      local_delivery_fraction: 0.8
      cpm_usd: 10
  o2o_journey:
    config:
      online_order_share: 0.25
      store_visit_rate: 0.2
  store_purchases:
    config:
      baseline_walk_ins: 1000
      purchase_capacity: 1500
  campaign_economics:
    config:
      online_basket_usd: 12
      store_basket_usd: 8
      gross_margin: 0.65
```

Tất cả đầu vào số phải hữu hạn: không chấp nhận `NaN` hay vô cực. Radius,
CPM và frequency cap phải lớn hơn 0; spend, mật độ audience, walk-in,
công suất và basket không âm. Fraction, rate, margin và index nằm trong
`[0, 1]`. Pydantic kiểm tra các giới hạn khi Dagster khởi tạo cấu hình op;
cấu hình sai làm lần chạy thất bại rõ ràng, không âm thầm thay giá trị.

`eligible_fraction` là tỷ lệ audience có thể tiếp cận hợp lệ và phù hợp
với chiến dịch; nó không xác minh sự đồng ý hay quyền sử dụng dữ liệu.
`local_delivery_fraction` là phần impressions mua bằng ngân sách thực sự
nằm trong vùng mục tiêu; nó không phải tỷ lệ audience đồng ý nhận marketing.

### Phương trình geo và O2O

Trong các phương trình sau, `I`, `V`, `O` và `F` dùng đơn vị thực, không
phải nghìn:

```text
eligible_audience = pi * radius_km^2 * audience_per_square_km * eligible_fraction
budget_impressions = spend_usd / cpm_usd * 1000
I = min(budget_impressions * local_delivery_fraction,
        eligible_audience * frequency_cap)
V = I * (0.02 + 0.03 * seasonality_index)
online_sessions = V * online_order_share
O = online_sessions * (0.02 + 0.03 * product_quality_index
                       + 0.01 * seasonality_index)
F = V * (1 - online_order_share) * store_visit_rate
store_conversion = 0.35 + 0.2 * product_quality_index + 0.1 * seasonality_index
baseline_demand = baseline_walk_ins * (0.5 + seasonality_index) * store_conversion
baseline_purchases = min(baseline_demand, purchase_capacity)
campaign_store_purchases = min(F * store_conversion,
                               purchase_capacity - baseline_purchases)
```

Catchment là hình tròn với mật độ đồng nhất; không mô hình hóa đường đi,
thời gian di chuyển, đối thủ hay ranh giới thực. Frequency cap giới hạn
tổng impressions bằng audience nhân tần suất; không bảo đảm giới hạn ở
cấp từng người. Impressions không đồng nghĩa với unique reach.

Baseline được ưu tiên công suất; campaign chỉ dùng phần còn lại. Vì vậy,
nếu cửa hàng đã đầy, thêm quảng cáo không tăng giao dịch tại cửa hàng.
`unserved_campaign_purchases` ghi nhu cầu campaign chưa phục vụ. Việc ưu
tiên baseline là giả định, không phải chính sách phân bổ khách thực tế.
Hai nhánh online và cửa hàng được giả định tách biệt; không có identity
resolution để khử trùng lặp giữa thiết bị, lượt ghé và POS.

### Kinh tế chiến dịch và kết quả mặc định

```text
baseline_revenue = baseline_purchases * store_basket_usd
simulated_incremental_revenue =
    O * online_basket_usd + campaign_store_purchases * store_basket_usd
total_revenue = baseline_revenue + simulated_incremental_revenue
simulated_incremental_contribution =
    simulated_incremental_revenue * gross_margin - spend_usd
simulated_roas = simulated_incremental_revenue / spend_usd
cost_per_campaign_purchase = spend_usd / (O + campaign_store_purchases)
```

**Toàn bộ spend cấu hình được tính vào chi phí**, kể cả khi audience cap
làm lượng hiển thị địa phương thấp hơn ngân sách có thể mua. Mô hình không
coi phần đó là tiền chưa chi hay tự động hoàn ngân sách.

Với cấu hình mặc định, kết quả xấp xỉ:

| Chỉ số | Giá trị |
| --- | ---: |
| Eligible audience | 9,424.78 |
| Local impressions | 28,274.33 |
| Website sessions | 989.60 |
| Online purchases | 11.38 |
| Campaign store visits | 148.44 |
| O2O purchases | 80.16 |
| Baseline store purchases | 540 |
| Total purchases (online + store) | 631.54 |
| Simulated incremental revenue | 777.83 USD |
| Simulated ROAS | 0.0778 |
| Simulated incremental contribution | -9,494.41 USD |

Ví dụ này cố ý cho thấy ngân sách quá lớn so với catchment không bảo đảm
hiệu quả kinh tế. Contribution chỉ trừ chi phí marketing sau gross margin;
không phải lợi nhuận ròng và chưa tách chi phí cố định, khuyến mại, thuế
hay phí giao hàng. Điều chỉnh basket và margin khi mô phỏng retail.

Spend bằng 0 cho ROAS `None`; không có campaign purchase cho cost per
purchase `None`. Đây là tỷ số không xác định, không phải 0 hay lỗi bị che
giấu. Audience hoặc local delivery bằng 0 vẫn giữ baseline; spend dương
lúc đó tạo contribution âm. Metrics được trả về từ op
`campaign_economics` và ghi vào log Dagster, không ghi vào bảng analytics.

### Chạy mô phỏng

Chọn `geo_marketing_sales_dag` trong Dagster Launchpad và dùng YAML trên.
Hoặc chạy trong môi trường Python của dự án, không cần dịch vụ dữ liệu:

```python
from dags_pipelines.causal_geo_marketing_dag import geo_marketing_sales_dag

result = geo_marketing_sales_dag.execute_in_process(
    run_config={
        "ops": {
            "marketing_spend": {"config": {"thousands_usd": 0.1}},
            "geo_ad_impressions": {"config": {"radius_km": 0.5}},
        }
    }
)
print(result.output_for_node("campaign_economics"))
```

So sánh các lần chạy với cùng seasonality, quality, kỳ phân tích và baseline,
chỉ thay biến can thiệp mong muốn. Giảm spend về 0 tạo baseline **theo giả
định mô hình**, không phải nhóm đối chứng đã đo.

## Log và giới hạn nhân quả

Mỗi op ghi đầu vào và kết quả qua `context.log.info(...)`; xem tab **Logs**
trong Dagster UI để theo dõi các nhánh online, store và economics. Các hệ
số được chọn để minh họa, chưa ước lượng từ dữ liệu. Mũi tên chỉ biểu thị
giả định, không chứng minh quan hệ nhân quả; chưa mô hình hóa nhiễu, sai
số hay độ bất định.

Đối với geo marketing, `simulated_incremental_*` chỉ là chênh lệch giữa hai
kịch bản giả định có và không có campaign. Mô hình giả định mọi chuyển đổi
trên nhánh campaign là bổ sung, baseline không bị cannibalization và không
có organic online sales. Không được diễn giải số này như causal lift đã
đo từ quảng cáo, coupon, lượt ghé hay last-click attribution.

Để chuyển sang đo lường thực tế, cần dữ liệu theo cửa hàng và kỳ thời gian
(spend, exposure, online events, footfall/POS, basket, margin, tồn kho và
công suất), định nghĩa cửa sổ attribution, và quy trình khử trùng lặp có
cơ sở pháp lý. Dùng geo holdout hoặc thử nghiệm ngẫu nhiên theo vùng/cửa
hàng khi khả thi; kiểm soát mùa vụ, thời tiết, đối thủ, xu hướng trước
chiến dịch và spillover giữa vùng. Phương pháp quan sát như difference-in-
differences cần kiểm tra giả định xu hướng song song. Không đưa dữ liệu
GPS hay định danh khách hàng vào mô hình minh họa này.
