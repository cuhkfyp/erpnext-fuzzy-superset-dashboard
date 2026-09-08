/* Source-level readiness and warning aggregates; never projects client data. */
WITH RECURSIVE registration_lineage AS (
    SELECT r.name AS current_registration, r.name AS source_name, r.amended_from, 0 AS depth
    FROM `tabCCD Registration` r
    WHERE r.docstatus = 1
    UNION ALL
    SELECT rl.current_registration, parent.name, parent.amended_from, rl.depth + 1
    FROM registration_lineage rl
    JOIN `tabCCD Registration` parent ON parent.name = rl.amended_from
    WHERE rl.depth < 100
),
resolved_registration AS (
    SELECT source_name, MAX(current_registration) AS current_registration
    FROM registration_lineage
    GROUP BY source_name
),
registration_roots AS (
    SELECT rl.current_registration, rl.source_name AS root_source
    FROM registration_lineage rl
    JOIN (
        SELECT current_registration, MAX(depth) AS max_depth
        FROM registration_lineage
        GROUP BY current_registration
    ) depth_by_current
      ON depth_by_current.current_registration = rl.current_registration
     AND depth_by_current.max_depth = rl.depth
),
source_universe AS (
    SELECT DISTINCT ccd_reg_source AS source
    FROM `tabCCD Master`
    WHERE COALESCE(ccd_reg_source, '') <> ''
    UNION
    SELECT root_source FROM registration_roots
),
mapping_readiness AS (
    SELECT
        rr.source_name,
        MAX(LOWER(TRIM(SUBSTRING_INDEX(f.sys_fieldname, ':', 1))) = 'sex') AS sex_mapping_ready,
        MAX(LOWER(TRIM(SUBSTRING_INDEX(f.sys_fieldname, ':', 1))) = 'birthday') AS dob_mapping_ready,
        MAX(LOWER(TRIM(SUBSTRING_INDEX(f.sys_fieldname, ':', 1))) = 'birthday_key') AS dob_key_mapping_ready,
        MAX(LOWER(TRIM(SUBSTRING_INDEX(f.sys_fieldname, ':', 1))) = 'res_district') AS residential_district_mapping_ready,
        MAX(LOWER(TRIM(SUBSTRING_INDEX(f.sys_fieldname, ':', 1))) IN
            ('post_district', 'pos_district')) AS postal_district_mapping_ready
    FROM resolved_registration rr
    LEFT JOIN `tabCCD Field Match` f
      ON f.parent = rr.current_registration
     AND f.parenttype = 'CCD Registration'
    GROUP BY rr.source_name
),
source_metadata AS (
    SELECT
        rr.source_name,
        COALESCE(r.custom_include_in_dashboard, 0) AS include_in_dashboard,
        NULLIF(TRIM(r.custom_dashboard_environment), '') AS environment,
        NULLIF(TRIM(r.service_name), '') AS registration_service,
        r.custom_service_available_from AS service_available_from,
        r.modified AS registration_modified
    FROM resolved_registration rr
    JOIN `tabCCD Registration` r ON r.name = rr.current_registration
),
row_quality AS (
    SELECT
        m.ccd_reg_source AS source,
        COUNT(*) AS source_row_count,
        SUM(NULLIF(TRIM(m.service_name), '') IS NOT NULL) AS row_service_populated,
        SUM(m.custom_service_start_date IS NOT NULL) AS service_start_populated_rows,
        SUM(m.birthday IS NOT NULL) AS dob_populated_rows,
        SUM(
            m.birthday IS NOT NULL
            AND m.birthday BETWEEN DATE_SUB(CURRENT_DATE, INTERVAL 120 YEAR) AND CURRENT_DATE
            AND LOWER(TRIM(COALESCE(m.birthday_key, ''))) NOT IN
                ('no', 'n', '0', 'false', 'estimated', 'estimate', 'approximate',
                 'non-actual', 'not actual', 'unknown')
        ) AS usable_dob_rows,
        SUM(
            m.birthday IS NOT NULL
            AND LOWER(TRIM(COALESCE(m.birthday_key, ''))) IN
                ('yes', 'y', '1', 'true', 'actual', 'verified')
        ) AS verified_dob_rows,
        SUM(
            m.birthday IS NOT NULL
            AND NULLIF(TRIM(COALESCE(m.birthday_key, '')), '') IS NULL
            AND m.birthday BETWEEN DATE_SUB(CURRENT_DATE, INTERVAL 120 YEAR) AND CURRENT_DATE
        ) AS plausible_unverified_dob_rows,
        SUM(
            m.birthday IS NOT NULL
            AND (m.birthday > CURRENT_DATE
                 OR m.birthday < DATE_SUB(CURRENT_DATE, INTERVAL 120 YEAR))
        ) AS invalid_dob_rows,
        SUM(
            LOWER(TRIM(COALESCE(m.birthday_key, ''))) IN
                ('yes', 'y', '1', 'true', 'actual', 'verified')
            AND m.birthday IS NULL
        ) AS birthday_mapping_defect_rows,
        SUM(UPPER(TRIM(COALESCE(m.sex, ''))) = 'M') AS stored_m_rows,
        SUM(NULLIF(TRIM(m.sex), '') IS NOT NULL) AS sex_populated_rows,
        SUM(
            UPPER(TRIM(COALESCE(m.res_district, ''))) IN
                ('CENTRAL AND WESTERN', 'CENTRAL & WESTERN', 'CW', '中西區',
                 'EASTERN', 'EST', '東區', 'SOUTHERN', 'SOU', '南區',
                 'WAN CHAI', 'WC', '灣仔區', 'KOWLOON CITY', 'KC', '九龍城區',
                 'KWUN TONG', 'KWT', '觀塘區', 'SHAM SHUI PO', 'SSP', '深水埗區',
                 'WONG TAI SIN', 'WTS', '黃大仙區', 'YAU TSIM MONG', 'YTM', '油尖旺區',
                 'ISLANDS', 'IS', '離島區', 'KWAI TSING', 'KUI', '葵青區',
                 'NORTH', 'NOR', '北區', 'SAI KUNG', 'SK', '西貢區',
                 'SHA TIN', 'ST', '沙田區', 'TAI PO', 'TP', '大埔區',
                 'TSUEN WAN', 'TW', '荃灣區', 'TUEN MUN', 'TM', '屯門區',
                 'YUEN LONG', 'YL', '元朗區')
            OR (
                UPPER(TRIM(COALESCE(m.post_district, ''))) IN
                    ('CENTRAL AND WESTERN', 'CENTRAL & WESTERN', 'CW', '中西區',
                     'EASTERN', 'EST', '東區', 'SOUTHERN', 'SOU', '南區',
                     'WAN CHAI', 'WC', '灣仔區', 'KOWLOON CITY', 'KC', '九龍城區',
                     'KWUN TONG', 'KWT', '觀塘區', 'SHAM SHUI PO', 'SSP', '深水埗區',
                     'WONG TAI SIN', 'WTS', '黃大仙區', 'YAU TSIM MONG', 'YTM', '油尖旺區',
                     'ISLANDS', 'IS', '離島區', 'KWAI TSING', 'KUI', '葵青區',
                     'NORTH', 'NOR', '北區', 'SAI KUNG', 'SK', '西貢區',
                     'SHA TIN', 'ST', '沙田區', 'TAI PO', 'TP', '大埔區',
                     'TSUEN WAN', 'TW', '荃灣區', 'TUEN MUN', 'TM', '屯門區',
                     'YUEN LONG', 'YL', '元朗區')
            )
        ) AS valid_district_rows,
        SUM(
            (NULLIF(TRIM(m.res_district), '') IS NOT NULL
             OR NULLIF(TRIM(m.post_district), '') IS NOT NULL)
            AND UPPER(TRIM(COALESCE(m.res_district, ''))) NOT IN
                ('CENTRAL AND WESTERN', 'CENTRAL & WESTERN', 'CW', '中西區',
                 'EASTERN', 'EST', '東區', 'SOUTHERN', 'SOU', '南區',
                 'WAN CHAI', 'WC', '灣仔區', 'KOWLOON CITY', 'KC', '九龍城區',
                 'KWUN TONG', 'KWT', '觀塘區', 'SHAM SHUI PO', 'SSP', '深水埗區',
                 'WONG TAI SIN', 'WTS', '黃大仙區', 'YAU TSIM MONG', 'YTM', '油尖旺區',
                 'ISLANDS', 'IS', '離島區', 'KWAI TSING', 'KUI', '葵青區',
                 'NORTH', 'NOR', '北區', 'SAI KUNG', 'SK', '西貢區',
                 'SHA TIN', 'ST', '沙田區', 'TAI PO', 'TP', '大埔區',
                 'TSUEN WAN', 'TW', '荃灣區', 'TUEN MUN', 'TM', '屯門區',
                 'YUEN LONG', 'YL', '元朗區')
            AND UPPER(TRIM(COALESCE(m.post_district, ''))) NOT IN
                ('CENTRAL AND WESTERN', 'CENTRAL & WESTERN', 'CW', '中西區',
                 'EASTERN', 'EST', '東區', 'SOUTHERN', 'SOU', '南區',
                 'WAN CHAI', 'WC', '灣仔區', 'KOWLOON CITY', 'KC', '九龍城區',
                 'KWUN TONG', 'KWT', '觀塘區', 'SHAM SHUI PO', 'SSP', '深水埗區',
                 'WONG TAI SIN', 'WTS', '黃大仙區', 'YAU TSIM MONG', 'YTM', '油尖旺區',
                 'ISLANDS', 'IS', '離島區', 'KWAI TSING', 'KUI', '葵青區',
                 'NORTH', 'NOR', '北區', 'SAI KUNG', 'SK', '西貢區',
                 'SHA TIN', 'ST', '沙田區', 'TAI PO', 'TP', '大埔區',
                 'TSUEN WAN', 'TW', '荃灣區', 'TUEN MUN', 'TM', '屯門區',
                 'YUEN LONG', 'YL', '元朗區')
        ) AS unmapped_location_rows,
        MAX(m.modified) AS latest_ccd_modified
    FROM `tabCCD Master` m
    GROUP BY m.ccd_reg_source
)
SELECT
    su.source,
    CASE
        WHEN su.source IN ('DT-NB181', 'BBBB-BBB', 'From-PJCHW') THEN 'Excluded'
        WHEN sm.include_in_dashboard = 1
         AND sm.environment IN ('Production', 'UAT', 'SIT', 'Development', 'Test') THEN 'Included'
        WHEN sm.environment IS NOT NULL THEN 'Excluded'
        ELSE 'Unclassified'
    END AS classification,
    COALESCE(sm.environment, 'Unclassified') AS environment,
    COALESCE(sm.include_in_dashboard, 0) AS include_in_dashboard,
    COALESCE(rq.source_row_count, 0) AS source_row_count,
    CASE WHEN COALESCE(rq.source_row_count, 0) > 0 THEN 1 ELSE 0 END AS populated_source,
    CASE
        WHEN sm.registration_service IS NOT NULL THEN 100.0
        WHEN COALESCE(rq.source_row_count, 0) = 0 THEN 0.0
        ELSE ROUND(100.0 * COALESCE(rq.row_service_populated, 0) / rq.source_row_count, 2)
    END AS service_metadata_coverage_pct,
    CASE
        WHEN COALESCE(rq.source_row_count, 0) = 0 THEN 0.0
        ELSE ROUND(
            100.0 * COALESCE(rq.service_start_populated_rows, 0) / rq.source_row_count,
            2
        )
    END AS service_start_coverage_pct,
    CASE
        WHEN COALESCE(rq.source_row_count, 0) = 0
            THEN 'Unavailable - no source rows'
        WHEN COALESCE(rq.service_start_populated_rows, 0) = 0
            THEN 'Unavailable - service start dates not populated'
        ELSE CONCAT(
            'Field populated - ',
            ROUND(100.0 * rq.service_start_populated_rows / rq.source_row_count, 2),
            '% coverage; validate retained history'
        )
    END AS growth_readiness,
    COALESCE(mr.sex_mapping_ready, 0) AS sex_mapping_ready,
    CASE
        WHEN COALESCE(mr.sex_mapping_ready, 0) = 0 THEN COALESCE(rq.stored_m_rows, 0)
        ELSE 0
    END AS placeholder_sex_rows,
    COALESCE(rq.sex_populated_rows, 0) AS stored_sex_rows,
    COALESCE(mr.dob_mapping_ready, 0) AS dob_mapping_ready,
    COALESCE(mr.dob_key_mapping_ready, 0) AS dob_key_mapping_ready,
    COALESCE(rq.dob_populated_rows, 0) AS dob_populated_rows,
    COALESCE(rq.usable_dob_rows, 0) AS usable_dob_rows,
    COALESCE(rq.verified_dob_rows, 0) AS verified_dob_rows,
    COALESCE(rq.plausible_unverified_dob_rows, 0) AS plausible_unverified_dob_rows,
    COALESCE(rq.invalid_dob_rows, 0) AS invalid_dob_rows,
    COALESCE(rq.birthday_mapping_defect_rows, 0) AS birthday_mapping_defect_rows,
    COALESCE(mr.residential_district_mapping_ready, 0) AS residential_district_mapping_ready,
    COALESCE(mr.postal_district_mapping_ready, 0) AS postal_district_mapping_ready,
    COALESCE(rq.valid_district_rows, 0) AS valid_district_rows,
    COALESCE(rq.unmapped_location_rows, 0) AS unmapped_location_rows,
    GREATEST(
        COALESCE(rq.source_row_count, 0) - COALESCE(rq.valid_district_rows, 0)
        - COALESCE(rq.unmapped_location_rows, 0),
        0
    ) AS missing_district_rows,
    sm.service_available_from,
    rq.latest_ccd_modified
FROM source_universe su
LEFT JOIN source_metadata sm ON sm.source_name = su.source
LEFT JOIN mapping_readiness mr ON mr.source_name = su.source
LEFT JOIN row_quality rq ON rq.source = su.source
