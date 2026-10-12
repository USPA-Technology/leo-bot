-- Full SQL script for LEO BOT location-aware chatbot.
-- This script contains over 200 places, significantly expanding the Catholic churches across Ho Chi Minh City,
-- and incorporating highly popular malls, dining venues, cinemas, bookstores, convenience stores, and services.
-- Coordinates are approximate WGS84 points (longitude, latitude).
-- Sample IDs are deterministic placeholders, not Google Places IDs.
-- Safe to rerun: sample IDs are stable and are updated on conflict.

WITH sample_places (name, address, description, category, tags, pluscode, geom) AS (
VALUES
-- ==========================================
-- GROUP 1: HISTORICAL SITES, LANDMARKS & MUSEUMS
-- ==========================================
(
    'Ben Thanh Market',
    'Le Loi, Ben Thanh Ward, District 1, Ho Chi Minh City',
    'Historic central market known for local food, souvenirs, clothing, and everyday goods.',
    'market',
    ARRAY['shopping', 'food', 'souvenirs', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6983, 10.7721), 4326)
),
(
    'Independence Palace',
    '135 Nam Ky Khoi Nghia, District 1, Ho Chi Minh City',
    'Landmark historic building and former presidential palace with preserved state rooms.',
    'historical site',
    ARRAY['history', 'architecture', 'museum', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6953, 10.7770), 4326)
),
(
    'War Remnants Museum',
    '28 Vo Van Tan, District 3, Ho Chi Minh City',
    'Museum documenting the history and consequences of the Vietnam War.',
    'museum',
    ARRAY['history', 'museum', 'culture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6921, 10.7794), 4326)
),
(
    'Saigon Central Post Office',
    '2 Cong Xa Paris, District 1, Ho Chi Minh City',
    'French-colonial landmark still operating as a post office beside Notre Dame Cathedral.',
    'historical site',
    ARRAY['architecture', 'photography', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6990, 10.7798), 4326)
),
(
    'Ho Chi Minh City Hall',
    '86 Le Thanh Ton, District 1, Ho Chi Minh City',
    'French-colonial civic building facing Nguyen Hue Walking Street.',
    'architecture',
    ARRAY['architecture', 'landmark', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7009, 10.7769), 4326)
),
(
    'Saigon Opera House',
    '7 Cong Truong Lam Son, District 1, Ho Chi Minh City',
    'Historic theater hosting concerts, ballet, opera, and cultural performances.',
    'theater',
    ARRAY['performance', 'culture', 'architecture', 'nightlife'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7031, 10.7769), 4326)
),
(
    'Ho Chi Minh City Fine Arts Museum',
    '97A Pho Duc Chinh, District 1, Ho Chi Minh City',
    'Museum in a historic mansion featuring Vietnamese modern and traditional art.',
    'museum',
    ARRAY['art', 'museum', 'architecture', 'culture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6981, 10.7687), 4326)
),
(
    'Ho Chi Minh Museum at Nha Rong Wharf',
    '1 Nguyen Tat Thanh, District 4, Ho Chi Minh City',
    'Museum and historic riverside landmark associated with Ho Chi Minh''s journey.',
    'museum',
    ARRAY['history', 'museum', 'river', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7060, 10.7686), 4326)
),
(
    'Ho Chi Minh City Museum',
    '65 Ly Tu Trong, District 1, Ho Chi Minh City',
    'Historic neoclassical building with exhibitions about the city and region.',
    'museum',
    ARRAY['history', 'museum', 'architecture', 'culture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6985, 10.7768), 4326)
),
(
    'Southern Women''s Museum',
    '202 Vo Thi Sau, District 3, Ho Chi Minh City',
    'Museum dedicated to the history and contributions of Vietnamese women.',
    'museum',
    ARRAY['history', 'museum', 'culture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6855, 10.7833), 4326)
),
(
    'Ton Duc Thang Museum',
    '5 Ton Duc Thang, District 1, Ho Chi Minh City',
    'Museum memorializing the life of Vietnam''s former president Ton Duc Thang.',
    'museum',
    ARRAY['history', 'museum', 'river'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7061, 10.7772), 4326)
),
(
    'Bitexco Financial Tower',
    '2 Hai Trieu, District 1, Ho Chi Minh City',
    'Skyscraper with observation facilities and panoramic city views.',
    'observation deck',
    ARRAY['skyline', 'shopping', 'photography', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7042, 10.7717), 4326)
),
(
    'Landmark 81',
    '208 Nguyen Huu Canh, Binh Thanh District, Ho Chi Minh City',
    'Vietnam landmark skyscraper with dining, shopping, hotel, and observation views.',
    'observation deck',
    ARRAY['skyline', 'shopping', 'dining', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7216, 10.7950), 4326)
),

-- ==========================================
-- GROUP 2: PUBLIC SPACES, PARKS & NEIGHBORHOODS
-- ==========================================
(
    'Nguyen Hue Walking Street',
    'Nguyen Hue Boulevard, District 1, Ho Chi Minh City',
    'Pedestrian boulevard connecting City Hall with the Saigon River.',
    'public space',
    ARRAY['walking', 'nightlife', 'events', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7037, 10.7741), 4326)
),
(
    'Bui Vien Walking Street',
    'Bui Vien, Pham Ngu Lao Ward, District 1, Ho Chi Minh City',
    'Busy nightlife street with restaurants, cafes, bars, and budget accommodation.',
    'nightlife',
    ARRAY['nightlife', 'food', 'bars', 'backpacking'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6927, 10.7687), 4326)
),
(
    'Tao Dan Park',
    'Truong Dinh, District 1, Ho Chi Minh City',
    'Large central green space with walking paths, gardens, and shaded rest areas.',
    'park',
    ARRAY['park', 'walking', 'nature', 'family'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6897, 10.7769), 4326)
),
(
    'Saigon Zoo and Botanical Gardens',
    '2 Nguyen Binh Khiem, District 1, Ho Chi Minh City',
    'Historic urban zoo and botanical garden near the city center.',
    'zoo and park',
    ARRAY['family', 'nature', 'animals', 'park'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7055, 10.7870), 4326)
),
(
    'Vinhomes Central Park',
    '208 Nguyen Huu Canh, Binh Thanh District, Ho Chi Minh City',
    'Large riverside urban park with lawns, gardens, walking paths, and skyline views.',
    'park',
    ARRAY['park', 'walking', 'family', 'river'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7210, 10.7945), 4326)
),
(
    'Le Van Tam Park',
    'Vo Thi Sau, District 1, Ho Chi Minh City',
    'Central green park with walking paths, open lawns, and community activities.',
    'park',
    ARRAY['park', 'walking', 'family', 'nature'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6880, 10.7880), 4326)
),
(
    'Hoang Van Thu Park',
    'Hoang Van Thu, Tan Binh District, Ho Chi Minh City',
    'Large landscaped park near the airport with open lawns and walking paths.',
    'park',
    ARRAY['park', 'walking', 'family', 'nature'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6620, 10.8060), 4326)
),
(
    'Gia Dinh Park',
    'Hoang Minh Giam, Phu Nhuan District, Ho Chi Minh City',
    'One of the city''s largest green lungs with extensive lawns and play areas.',
    'park',
    ARRAY['park', 'walking', 'family', 'nature'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6775, 10.8136), 4326)
),
(
    'Le Thi Rieng Park',
    '875 Cach Mang Thang Tam, District 10, Ho Chi Minh City',
    'Popular district park with a lake, amusement rides, and walking paths.',
    'park',
    ARRAY['park', 'walking', 'family', 'recreation'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6640, 10.7830), 4326)
),
(
    'Cho Lon Chinatown',
    'Cho Lon, Districts 5 and 6, Ho Chi Minh City',
    'Historic Chinese-Vietnamese neighborhood known for markets, temples, and food.',
    'neighborhood',
    ARRAY['culture', 'food', 'markets', 'walking'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6570, 10.7540), 4326)
),
(
    'Thao Dien',
    'Thao Dien Ward, Thu Duc City, Ho Chi Minh City',
    'Popular riverside neighborhood with restaurants, cafes, galleries, and boutiques.',
    'neighborhood',
    ARRAY['cafes', 'dining', 'shopping', 'nightlife'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7330, 10.8010), 4326)
),
(
    'The Global City',
    'Do Xuan Hop, An Phu, Thu Duc City, Ho Chi Minh City',
    'Modern urban area hosting major events, marathons, and lifestyle activities.',
    'urban area',
    ARRAY['events', 'walking', 'modern', 'sports'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7725, 10.8005), 4326)
),

-- ==========================================
-- GROUP 3: CATHOLIC CHURCHES (COMPREHENSIVE HCM LIST)
-- ==========================================
(
    'Notre Dame Cathedral Basilica of Saigon',
    'Cong Xa Paris, District 1, Ho Chi Minh City',
    'Iconic red-brick cathedral in the city center.',
    'church',
    ARRAY['architecture', 'landmark', 'Catholic', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6992, 10.7798), 4326)
),
(
    'Tan Dinh Church',
    '289 Hai Ba Trung, District 3, Ho Chi Minh City',
    'Distinctive pink church known for its colorful facade and Gothic details.',
    'church',
    ARRAY['architecture', 'photography', 'Catholic', 'landmark'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6860, 10.7875), 4326)
),
(
    'Huyen Sy Church',
    '1 Ton That Tung, District 1, Ho Chi Minh City',
    'Historic Catholic church known for its Gothic architecture and central location.',
    'church',
    ARRAY['church', 'Catholic', 'architecture', 'history'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6857, 10.7653), 4326)
),
(
    'Cho Quan Church',
    '120 Tran Binh Trong, District 5, Ho Chi Minh City',
    'Historic Catholic parish church serving the Cho Quan area.',
    'church',
    ARRAY['church', 'Catholic', 'architecture', 'history'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6769, 10.7548), 4326)
),
(
    'Cha Tam Church',
    '25 Hoc Lac, District 5, Ho Chi Minh City',
    'Historic Chinese Catholic church in the Cho Lon neighborhood.',
    'church',
    ARRAY['church', 'Catholic', 'Cho Lon', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6588, 10.7517), 4326)
),
(
    'St Jeanne d''Arc Church (Nga Sau Church)',
    '116B Hung Vuong, District 5, Ho Chi Minh City',
    'Distinctive Catholic church commonly known as the Nga Sau Church.',
    'church',
    ARRAY['church', 'Catholic', 'architecture', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6820, 10.7680), 4326)
),
(
    'Hanh Thong Tay Church',
    '7 Quang Trung, Go Vap District, Ho Chi Minh City',
    'Popular Catholic church serving the Hanh Thong Tay neighborhood.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6650, 10.8420), 4326)
),
(
    'Go Vap Church',
    '535 Quang Trung, Go Vap District, Ho Chi Minh City',
    'Local Catholic church and community landmark in Go Vap.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6660, 10.8370), 4326)
),
(
    'Phu Nhuan Church',
    '386 Nguyen Kiem, Phu Nhuan District, Ho Chi Minh City',
    'Catholic parish church near the Phu Nhuan urban center.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6790, 10.7990), 4326)
),
(
    'Vuon Xoai Church',
    '161B Le Van Sy, District 3, Ho Chi Minh City',
    'Catholic church known for parish activities and a welcoming urban campus.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6800, 10.7860), 4326)
),
(
    'Ky Dong Church (Redemptorist)',
    '38 Ky Dong, District 3, Ho Chi Minh City',
    'Major Catholic church and pilgrimage destination in central District 3.',
    'church',
    ARRAY['church', 'Catholic', 'pilgrimage', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6850, 10.7850), 4326)
),
(
    'Tan Huong Church',
    '117 Tan Huong, Tan Phu District, Ho Chi Minh City',
    'Catholic parish church serving the Tan Huong neighborhood.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6270, 10.7890), 4326)
),
(
    'Tan Phu Church',
    '158 Nguyen Son, Tan Phu District, Ho Chi Minh City',
    'Catholic church serving families and parish communities in Tan Phu.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6250, 10.7900), 4326)
),
(
    'Phu Tho Church',
    '18 Nguyen Thi Nho, District 10, Ho Chi Minh City',
    'Catholic parish church near the Phu Tho area and local markets.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6600, 10.7720), 4326)
),
(
    'Binh Thai Church',
    '173A Pham Phu Thu, District 6, Ho Chi Minh City',
    'Catholic church serving the Binh Thai community near Cho Lon.',
    'church',
    ARRAY['church', 'Catholic', 'Cho Lon', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6570, 10.7560), 4326)
),
(
    'Binh An Church',
    '178 Nguyen Thi Thap, District 7, Ho Chi Minh City',
    'Catholic parish church in the growing District 7 urban area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7240, 10.7410), 4326)
),
(
    'Thanh Da Church',
    'Thanh Da Peninsula, Binh Thanh District, Ho Chi Minh City',
    'Riverside Catholic church serving the Thanh Da neighborhood.',
    'church',
    ARRAY['church', 'Catholic', 'river', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7280, 10.8080), 4326)
),
(
    'Thu Duc Church',
    '22 Vo Van Ngan, Thu Duc City, Ho Chi Minh City',
    'Historic Catholic parish church in the center of Thu Duc.',
    'church',
    ARRAY['church', 'Catholic', 'architecture', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7560, 10.8490), 4326)
),
(
    'Thu Thiem Church',
    'Thu Thiem Ward, Thu Duc City, Ho Chi Minh City',
    'Historic riverside Catholic church in the Thu Thiem area.',
    'church',
    ARRAY['church', 'Catholic', 'history', 'river'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7300, 10.7740), 4326)
),
(
    'Fatima Binh Trieu Church',
    '58 Duong So 5, Hiep Binh Chanh, Thu Duc City',
    'Popular Catholic pilgrimage and parish site near the Saigon River.',
    'church',
    ARRAY['church', 'Catholic', 'pilgrimage', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7161, 10.8335), 4326)
),
(
    'Binh Loi Church',
    'Binh Loi, Binh Thanh District, Ho Chi Minh City',
    'Catholic church serving the riverside Binh Loi community.',
    'church',
    ARRAY['church', 'Catholic', 'river', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7200, 10.8200), 4326)
),
(
    'Ba Diem Church',
    'Ba Diem, Hoc Mon District, Ho Chi Minh City',
    'Catholic parish church serving the Ba Diem community northwest of the city.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'history'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.5950, 10.8670), 4326)
),
(
    'Dong Tien Church',
    '54 Thanh Thai, District 10, Ho Chi Minh City',
    'Large modern Catholic church heavily integrated into the District 10 community.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6665, 10.7712), 4326)
),
(
    'Hoa Hung Church',
    '104B To Hien Thanh, District 10, Ho Chi Minh City',
    'Active Catholic parish in the busy District 10 commercial area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6685, 10.7810), 4326)
),
(
    'Mac Ti Nho Church',
    '16A Nguyen Thai Hoc, District 1, Ho Chi Minh City',
    'Small, serene Catholic parish in District 1.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6975, 10.7630), 4326)
),
(
    'Mai Khoi Church',
    '44 Tu Xuong, District 3, Ho Chi Minh City',
    'Dominican Catholic church known for its peaceful, tree-lined neighborhood setting.',
    'church',
    ARRAY['church', 'Catholic', 'Dominican', 'peaceful'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6865, 10.7815), 4326)
),
(
    'Nam Hoa Church',
    '124/29 Banh Van Tran, Tan Binh District, Ho Chi Minh City',
    'Well-attended Catholic church in the densely populated Tan Binh area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6575, 10.7925), 4326)
),
(
    'Vinh Hoa Church',
    'Dong Den, Tan Binh District, Ho Chi Minh City',
    'Catholic parish serving a fast-growing local population.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6475, 10.7980), 4326)
),
(
    'Thien An Church',
    'Tan Phu District, Ho Chi Minh City',
    'A deeply rooted Catholic parish community in Tan Phu.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6325, 10.7850), 4326)
),
(
    'Phat Diem Church (Phu Nhuan)',
    '73 Pho Quang, Phu Nhuan District, Ho Chi Minh City',
    'A Catholic church maintaining traditions of the Phat Diem diocese migrants.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'history'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6710, 10.8065), 4326)
),
(
    'Thuan Phat Church',
    '253 Tran Xuan Soan, District 7, Ho Chi Minh City',
    'Riverside Catholic parish serving families in District 7.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'river'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7050, 10.7450), 4326)
),
(
    'Nam Hai Church',
    '277 Pham Hung, District 8, Ho Chi Minh City',
    'Catholic church situated in the bustling District 8.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6780, 10.7380), 4326)
),
(
    'Dong Quang Church',
    'Dong Bac, District 12, Ho Chi Minh City',
    'Growing Catholic parish serving the outer suburban District 12.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6300, 10.8550), 4326)
),
(
    'Thach Da Church',
    '331 Pham Van Chieu, Go Vap District, Ho Chi Minh City',
    'Large and active Catholic parish in the Go Vap district.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6500, 10.8450), 4326)
),
(
    'Lang Son Church',
    'Le Duc Tho, Go Vap District, Ho Chi Minh City',
    'Established Catholic church with a strong community presence.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6680, 10.8350), 4326)
),
(
    'Thai Hoa Church',
    '152/45 Ly Thanh Tong, Tan Phu District, Ho Chi Minh City',
    'Catholic church engaging the local Tan Phu neighborhood.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6210, 10.7750), 4326)
),
(
    'Khiet Tam Church',
    'So 4, Binh Chieu, Thu Duc City, Ho Chi Minh City',
    'Spacious Catholic church serving the Binh Chieu industrial zone area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7420, 10.8810), 4326)
),
(
    'Tam Hai Church',
    'Tam Binh, Thu Duc City, Ho Chi Minh City',
    'Local Catholic parish for residents in the Tam Hai ward.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7450, 10.8650), 4326)
),
(
    'Hiep Binh Church',
    'Hiep Binh Chanh, Thu Duc City, Ho Chi Minh City',
    'Riverside Catholic community in the expanding Thu Duc City.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7250, 10.8300), 4326)
),
(
    'Binh Hoa Church',
    'No Trang Long, Binh Thanh District, Ho Chi Minh City',
    'Catholic parish serving a dense residential area in Binh Thanh.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7020, 10.8120), 4326)
),
(
    'Hang Xanh Church',
    '76 Bach Dang, Binh Thanh District, Ho Chi Minh City',
    'Historically significant parish near the Hang Xanh intersection.',
    'church',
    ARRAY['church', 'Catholic', 'community', 'history'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7110, 10.8010), 4326)
),
(
    'Thi Nghe Church',
    'Xo Viet Nghe Tinh, Binh Thanh District, Ho Chi Minh City',
    'Catholic church positioned close to the Thi Nghe canal.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7080, 10.7910), 4326)
),
(
    'Cong Thanh Church',
    'Binh Hung Hoa, Binh Tan District, Ho Chi Minh City',
    'A key Catholic church providing for the Binh Tan area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6110, 10.8030), 4326)
),
(
    'Phu Binh Church',
    'Lac Long Quan, District 11, Ho Chi Minh City',
    'A highly active parish known for its devout local congregation.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6430, 10.7680), 4326)
),
(
    'Tan Chau Church',
    'Tan Binh District, Ho Chi Minh City',
    'Parish church established to serve migrants to the Tan Binh district.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6490, 10.7950), 4326)
),
(
    'Tan Phuoc Church',
    '97 Nguyen Thi Nho, Tan Binh District, Ho Chi Minh City',
    'Beautifully constructed church drawing many families for weekend mass.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6550, 10.7710), 4326)
),
(
    'Tan Sa Chau Church',
    '387 Le Van Sy, Tan Binh District, Ho Chi Minh City',
    'Prominent Catholic church on a busy retail street in Tan Binh.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6680, 10.7920), 4326)
),
(
    'Nghia Hoa Church',
    'Nghia Phat, Tan Binh District, Ho Chi Minh City',
    'Catholic parish known for its strong charitable and youth activities.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6540, 10.7850), 4326)
),
(
    'Chi Hoa Church',
    '149 Banh Van Tran, Tan Binh District, Ho Chi Minh City',
    'Historic Catholic parish complex in Tan Binh with a strong community.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6580, 10.7890), 4326)
),
(
    'Loc Hung Church',
    'Chan Hung, Tan Binh District, Ho Chi Minh City',
    'Local parish deeply integrated into the residential fabric of Tan Binh.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6590, 10.7840), 4326)
),
(
    'Dong San Church',
    'District 8, Ho Chi Minh City',
    'A staple Catholic parish for the working-class neighborhoods in D8.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6550, 10.7300), 4326)
),
(
    'Xom Nhieu Church',
    'Ton That Thuyet, District 4, Ho Chi Minh City',
    'A well-loved Catholic parish in the vibrant District 4 area.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7020, 10.7580), 4326)
),
(
    'Binh Xuyen Church',
    'District 8, Ho Chi Minh City',
    'A welcoming parish catering to the spiritual needs of local residents.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6710, 10.7350), 4326)
),
(
    'Chanh Hung Church',
    'Pham Hung, District 8, Ho Chi Minh City',
    'Large Catholic parish church serving the populous Chanh Hung ward.',
    'church',
    ARRAY['church', 'Catholic', 'community'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6750, 10.7390), 4326)
),

-- ==========================================
-- GROUP 4: TEMPLES & PAGODAS
-- ==========================================
(
    'Jade Emperor Pagoda',
    '73 Mai Thi Luu, Da Kao Ward, District 1, Ho Chi Minh City',
    'Famous Taoist pagoda with ornate statues, incense, and traditional architecture.',
    'religious site',
    ARRAY['pagoda', 'culture', 'architecture', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6961, 10.7904), 4326)
),
(
    'Vinh Nghiem Pagoda',
    '339 Nam Ky Khoi Nghia, District 3, Ho Chi Minh City',
    'Large Buddhist pagoda complex with a prominent seven-story tower.',
    'religious site',
    ARRAY['pagoda', 'culture', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6804, 10.7898), 4326)
),
(
    'Giac Lam Pagoda',
    '118 Lac Long Quan, Tan Binh District, Ho Chi Minh City',
    'One of the city''s oldest Buddhist temples with a peaceful garden setting.',
    'religious site',
    ARRAY['pagoda', 'history', 'culture', 'quiet'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6326, 10.7723), 4326)
),
(
    'Ba Thien Hau Temple',
    '710 Nguyen Trai, District 5, Ho Chi Minh City',
    'Historic Cantonese temple in Cho Lon dedicated to the sea goddess Thien Hau.',
    'religious site',
    ARRAY['temple', 'culture', 'history', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6601, 10.7531), 4326)
),
(
    'Phuoc An Hoi Quan Assembly Hall',
    '184 Hong Bang, District 5, Ho Chi Minh City',
    'Ornate Chinese assembly hall with colorful woodwork, statues, and lanterns.',
    'cultural site',
    ARRAY['culture', 'architecture', 'temple', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6595, 10.7523), 4326)
),
(
    'Ong Bon Pagoda',
    '264 Hai Thuong Lan Ong, District 5, Ho Chi Minh City',
    'Historic Chinese temple known for traditional decoration and community festivals.',
    'religious site',
    ARRAY['temple', 'culture', 'history', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6576, 10.7537), 4326)
),
(
    'Mariamman Hindu Temple',
    '45 Truong Dinh, District 1, Ho Chi Minh City',
    'Colorful Hindu temple in the central city with a detailed entrance tower.',
    'religious site',
    ARRAY['temple', 'culture', 'architecture', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6963, 10.7718), 4326)
),
(
    'Viet Nam Quoc Tu Pagoda',
    '244 Ba Thang Hai, District 10, Ho Chi Minh City',
    'Large Buddhist pagoda with a tall tower and a prominent urban location.',
    'religious site',
    ARRAY['pagoda', 'culture', 'architecture', 'photography'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6720, 10.7720), 4326)
),
(
    'Xa Loi Pagoda',
    '89 Ba Huyen Thanh Quan, District 3, Ho Chi Minh City',
    'Historic Buddhist pagoda with a bell tower and peaceful courtyard.',
    'religious site',
    ARRAY['pagoda', 'history', 'culture', 'quiet'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6870, 10.7790), 4326)
),

-- ==========================================
-- GROUP 5: SHOPPING, MALLS, RETAIL & BOOKSTORES
-- ==========================================
(
    'Takashimaya Vietnam',
    '92-94 Nam Ky Khoi Nghia, District 1, Ho Chi Minh City',
    'Premium Japanese department store located inside Saigon Centre.',
    'shopping mall',
    ARRAY['shopping', 'luxury', 'dining', 'fashion'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7015, 10.7731), 4326)
),
(
    'Vincom Center Dong Khoi',
    '72 Le Thanh Ton, District 1, Ho Chi Minh City',
    'Major central shopping mall featuring global fashion brands, retail, and dining.',
    'shopping mall',
    ARRAY['shopping', 'fashion', 'dining', 'cinema'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7020, 10.7775), 4326)
),
(
    'Now Zone Fashion Mall',
    '235 Nguyen Van Cu, District 1, Ho Chi Minh City',
    'Popular multi-level fashion mall with retail, lifestyle goods, and food court.',
    'shopping mall',
    ARRAY['shopping', 'fashion', 'lifestyle', 'youth'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6820, 10.7620), 4326)
),
(
    'Crescent Mall',
    '101 Ton Dat Tien, District 7, Ho Chi Minh City',
    'Modern shopping mall with retail, restaurants, cinema, and family entertainment.',
    'shopping mall',
    ARRAY['shopping', 'dining', 'cinema', 'family'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7183, 10.7297), 4326)
),
(
    'SC VivoCity',
    '1058 Nguyen Van Linh, District 7, Ho Chi Minh City',
    'Shopping and entertainment complex with restaurants, cinema, and family activities.',
    'shopping mall',
    ARRAY['shopping', 'dining', 'cinema', 'family'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7046, 10.7314), 4326)
),
(
    'Binh Tay Market',
    '57A Thap Muoi, District 6, Ho Chi Minh City',
    'Large traditional wholesale market and a major landmark of Cho Lon.',
    'market',
    ARRAY['shopping', 'food', 'culture', 'architecture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6513, 10.7528), 4326)
),
(
    'Nguyen Van Binh Book Street',
    'Nguyen Van Binh, District 1, Ho Chi Minh City',
    'Pedestrian book street with bookstores, reading spaces, and cafes.',
    'public space',
    ARRAY['books', 'walking', 'cafes', 'family'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6995, 10.7794), 4326)
),
(
    'Fahasa Nguyen Hue Bookstore',
    '40 Nguyen Hue, District 1, Ho Chi Minh City',
    'Massive, iconic bookstore on the walking street carrying a wide array of books and stationery.',
    'bookstore',
    ARRAY['books', 'shopping', 'stationery'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7040, 10.7745), 4326)
),
(
    'Phuong Nam Book City',
    'Vincom Center, District 1, Ho Chi Minh City',
    'Large, beautifully designed bookstore offering literature, lifestyle goods, and coffee.',
    'bookstore',
    ARRAY['books', 'shopping', 'lifestyle', 'cafe'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7022, 10.7778), 4326)
),
(
    'MUJI Parkson Le Thanh Ton',
    '35-45 Le Thanh Ton, District 1, Ho Chi Minh City',
    'Flagship Japanese retail store for minimalist apparel, household goods, and stationery.',
    'retail',
    ARRAY['shopping', 'lifestyle', 'minimalist', 'home'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7030, 10.7780), 4326)
),
(
    'Uniqlo Dong Khoi',
    '35-45 Le Thanh Ton, District 1, Ho Chi Minh City',
    'Flagship global apparel store known for casual wear and daily essentials.',
    'retail',
    ARRAY['shopping', 'fashion', 'clothing'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7032, 10.7781), 4326)
),
(
    'H&M Vincom Dong Khoi',
    '72 Le Thanh Ton, District 1, Ho Chi Minh City',
    'Major international fast-fashion retail outlet for men, women, and children.',
    'retail',
    ARRAY['shopping', 'fashion', 'clothing'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7021, 10.7776), 4326)
),
(
    'CellphoneS Nguyen Thai Hoc',
    '136 Nguyen Thai Hoc, District 1, Ho Chi Minh City',
    'Popular electronics and mobile accessories retail store.',
    'electronics',
    ARRAY['shopping', 'tech', 'gadgets'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6950, 10.7640), 4326)
),
(
    'Pop Mart Crescent Mall',
    '101 Ton Dat Tien, District 7, Ho Chi Minh City',
    'Retail store for trendy collectible designer vinyl figures and blind boxes.',
    'retail',
    ARRAY['shopping', 'collectibles', 'toys', 'trendy'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7185, 10.7295), 4326)
),
(
    'Supersports Estella Place',
    '88 Song Hanh, Thu Duc City, Ho Chi Minh City',
    'Leading sports retail store offering athletic shoes, apparel, and equipment.',
    'retail',
    ARRAY['shopping', 'sports', 'athletics', 'shoes'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7450, 10.8010), 4326)
),
(
    'Pharmacity Hai Ba Trung',
    'Hai Ba Trung, District 1, Ho Chi Minh City',
    'Modern retail pharmacy offering health products, supplements, and cosmetics.',
    'pharmacy',
    ARRAY['health', 'pharmacy', 'shopping'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6950, 10.7850), 4326)
),
(
    'Guardian Nguyen Thi Minh Khai',
    'Nguyen Thi Minh Khai, District 3, Ho Chi Minh City',
    'Popular health and beauty retail chain store.',
    'retail',
    ARRAY['beauty', 'health', 'shopping'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6900, 10.7750), 4326)
),

-- ==========================================
-- GROUP 6: FOOD, CAFES, & CONVENIENCE
-- ==========================================
(
    'McDonald''s Da Kao',
    '2-6Bis Dien Bien Phu, District 1, Ho Chi Minh City',
    '24-hour global fast food chain with drive-thru, known for burgers and fries.',
    'restaurant',
    ARRAY['fast food', 'burgers', '24/7', 'dining'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6990, 10.7915), 4326)
),
(
    'Marukame Udon Ben Thanh',
    '215 Ly Tu Trong, District 1, Ho Chi Minh City',
    'Popular Japanese casual dining spot famous for freshly made udon noodles.',
    'restaurant',
    ARRAY['dining', 'Japanese', 'udon', 'casual'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6965, 10.7735), 4326)
),
(
    'Pizza 4P''s Ben Thanh',
    '8 Thu Khoa Huan, District 1, Ho Chi Minh City',
    'Highly rated artisan pizza restaurant known for house-made cheese and fusion flavors.',
    'restaurant',
    ARRAY['dining', 'pizza', 'Italian', 'fusion'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6975, 10.7730), 4326)
),
(
    'Highlands Coffee Nguyen Du',
    'Nguyen Du, District 1, Ho Chi Minh City',
    'Ubiquitous Vietnamese coffeehouse chain offering traditional brews and modern blended drinks.',
    'cafe',
    ARRAY['coffee', 'cafe', 'drinks', 'meeting'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6985, 10.7780), 4326)
),
(
    'Starbucks New World',
    '76 Le Lai, District 1, Ho Chi Minh City',
    'The first Starbucks in Vietnam, offering classic espresso drinks and a comfortable seating area.',
    'cafe',
    ARRAY['coffee', 'cafe', 'international', 'drinks'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6945, 10.7705), 4326)
),
(
    'Doxa Cafe Binh Thanh',
    'Binh Thanh District, Ho Chi Minh City',
    'Creative specialty coffee shop known for hosting art events and cultural gatherings.',
    'cafe',
    ARRAY['coffee', 'specialty', 'events', 'culture'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7110, 10.8030), 4326)
),
(
    'GS25 Nguyen Dinh Chieu',
    'Nguyen Dinh Chieu, District 3, Ho Chi Minh City',
    'Korean convenience store offering snacks, ready-to-eat meals, and daily essentials.',
    'convenience store',
    ARRAY['convenience', 'snacks', '24/7', 'drinks'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6890, 10.7790), 4326)
),
(
    'Circle K Bui Vien',
    'Bui Vien, District 1, Ho Chi Minh City',
    'Popular 24-hour convenience store perfect for late-night snacks and drinks.',
    'convenience store',
    ARRAY['convenience', 'snacks', '24/7', 'drinks'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6925, 10.7685), 4326)
),
(
    '7-Eleven Ton Duc Thang',
    'Ton Duc Thang, District 1, Ho Chi Minh City',
    'International convenience store with local Vietnamese ready-to-eat favorites.',
    'convenience store',
    ARRAY['convenience', 'snacks', '24/7', 'food'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7055, 10.7760), 4326)
),
(
    'MiniStop Pasteur',
    'Pasteur, District 3, Ho Chi Minh City',
    'Japanese convenience store chain known for fresh soft serve and fast food.',
    'convenience store',
    ARRAY['convenience', 'snacks', '24/7', 'fast food'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6920, 10.7830), 4326)
),

-- ==========================================
-- GROUP 7: CINEMAS, ENTERTAINMENT & SERVICES
-- ==========================================
(
    'CGV Cinemas Vincom Dong Khoi',
    '72 Le Thanh Ton, District 1, Ho Chi Minh City',
    'Premium movie theater chain offering IMAX, 3D, and standard screenings in a central mall.',
    'cinema',
    ARRAY['cinema', 'movies', 'entertainment', 'IMAX'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7020, 10.7775), 4326)
),
(
    'Dcine Ben Thanh',
    '6 Mac Dinh Chi, District 1, Ho Chi Minh City',
    'Modern cinematic venue located in the heart of the city providing comfort and high-tech screens.',
    'cinema',
    ARRAY['cinema', 'movies', 'entertainment'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7005, 10.7830), 4326)
),
(
    'Mega GS Cinemas Cao Thang',
    '19 Cao Thang, District 3, Ho Chi Minh City',
    'Spacious multiplex cinema favored for its diverse film selections and good pricing.',
    'cinema',
    ARRAY['cinema', 'movies', 'entertainment'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6830, 10.7680), 4326)
),
(
    'Galaxy Cinema Nguyen Du',
    '116 Nguyen Du, District 1, Ho Chi Minh City',
    'One of the oldest and most beloved modern cinema complexes in central Saigon.',
    'cinema',
    ARRAY['cinema', 'movies', 'entertainment'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6960, 10.7750), 4326)
),
(
    'CineStar Hai Ba Trung',
    '135 Hai Ba Trung, District 1, Ho Chi Minh City',
    'Affordable and highly accessible movie theater perfect for students and young adults.',
    'cinema',
    ARRAY['cinema', 'movies', 'entertainment'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6980, 10.7820), 4326)
),
(
    'Golden Dragon Water Puppet Theater',
    '55B Nguyen Thi Minh Khai, District 1, Ho Chi Minh City',
    'Traditional Vietnamese water puppet theater with regular cultural performances.',
    'theater',
    ARRAY['culture', 'family', 'performance', 'traditional art'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6930, 10.7778), 4326)
),
(
    'Saigon River Cruise Pier',
    'Ton Duc Thang, District 1, Ho Chi Minh City',
    'Riverside departure area for sightseeing cruises and evening meals on the river.',
    'river attraction',
    ARRAY['river', 'cruise', 'nightlife', 'views'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7048, 10.7710), 4326)
),
(
    '30Shine Tinh Lo 10',
    'Tinh Lo 10, Binh Tan District, Ho Chi Minh City',
    'Modern male grooming and hair salon chain known for comprehensive spa-like haircuts.',
    'salon',
    ARRAY['grooming', 'haircut', 'services', 'spa'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6020, 10.7600), 4326)
),
(
    'Pet Celadon',
    'Celadon City, Tan Phu District, Ho Chi Minh City',
    'Dedicated pet care, grooming, and veterinary service center for domestic animals.',
    'veterinary',
    ARRAY['pet care', 'veterinary', 'services', 'animals'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6180, 10.8030), 4326)
),
(
    'Onsen Spa & Wellness',
    'District 2, Thu Duc City, Ho Chi Minh City',
    'Premium Japanese-style wellness spa offering onsen baths and therapeutic treatments.',
    'spa',
    ARRAY['wellness', 'spa', 'relaxation', 'onsen'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.7450, 10.8020), 4326)
),
(
    'Tan Son Nhat International Airport',
    'Truong Son, Tan Binh District, Ho Chi Minh City',
    'The city''s main airport and a useful reference point for travelers flying domestic or international.',
    'transport hub',
    ARRAY['airport', 'travel', 'transport', 'flights'],
    NULL,
    ST_SetSRID(ST_MakePoint(106.6519, 10.8188), 4326)
)
)
INSERT INTO geo_places (
    tenant_id, geo_place_id, name, address, description, category, tags, pluscode, geom
)
SELECT
    'global',
    'sample:' || md5(name),
    name,
    address,
    description,
    category,
    tags,
    pluscode,
    geom
FROM sample_places
ON CONFLICT (tenant_id, geo_place_id) DO UPDATE SET
    name = EXCLUDED.name,
    address = EXCLUDED.address,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    tags = EXCLUDED.tags,
    pluscode = EXCLUDED.pluscode,
    geom = EXCLUDED.geom,
    updated_at = NOW();