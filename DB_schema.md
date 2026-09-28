## Table `alembic_version`

### Columns

| Name          | Type      | Constraints |
| ------------- | --------- | ----------- |
| `version_num` | `varchar` | Primary     |

## Table `code_domain`

### Columns

| Name          | Type      | Constraints |
| ------------- | --------- | ----------- |
| `id`          | `int4`    | Primary     |
| `code`        | `varchar` | Unique      |
| `label`       | `varchar` | Nullable    |
| `description` | `text`    | Nullable    |

## Table `disturbance`

### Columns

| Name                | Type          | Constraints |
| ------------------- | ------------- | ----------- |
| `id`                | `int4`        | Primary     |
| `disturbance_id`    | `varchar`     | Unique      |
| `name`              | `varchar`     | Nullable    |
| `region`            | `varchar`     | Nullable    |
| `season`            | `varchar`     | Nullable    |
| `type_code`         | `varchar`     | Nullable    |
| `is_test`           | `bool`        |             |
| `has_watch`         | `bool`        |             |
| `has_warning`       | `bool`        |             |
| `has_best_track`    | `bool`        |             |
| `bulletin_count`    | `int4`        |             |
| `observation_count` | `int4`        |             |
| `first_issue`       | `timestamptz` | Nullable    |
| `last_issue`        | `timestamptz` | Nullable    |
| `first_obs_tm`      | `timestamptz` | Nullable    |
| `last_obs_tm`       | `timestamptz` | Nullable    |
| `created_at`        | `timestamptz` |             |

## Table `ingest_run`

### Columns

| Name           | Type          | Constraints |
| -------------- | ------------- | ----------- |
| `id`           | `int4`        | Primary     |
| `created_at`   | `timestamptz` |             |
| `finished_at`  | `timestamptz` | Nullable    |
| `kind`         | `varchar`     |             |
| `source`       | `text`        | Nullable    |
| `status`       | `varchar`     |             |
| `rows_read`    | `int4`        |             |
| `rows_written` | `int4`        |             |
| `rows_skipped` | `int4`        |             |
| `error`        | `text`        | Nullable    |
| `code_version` | `varchar`     | Nullable    |
| `stats`        | `jsonb`       | Nullable    |

## Table `interpolation_run`

### Columns

| Name                          | Type          | Constraints |
| ----------------------------- | ------------- | ----------- |
| `id`                          | `int4`        | Primary     |
| `created_at`                  | `timestamptz` |             |
| `label`                       | `varchar`     | Nullable    |
| `source_dataset`              | `varchar`     |             |
| `step_minutes`                | `int4`        |             |
| `project_start`               | `timestamptz` | Nullable    |
| `gf_threshold_kn`             | `float8`      |             |
| `sf_threshold_kn`             | `float8`      |             |
| `hf_threshold_kn`             | `float8`      |             |
| `mps_to_knots`                | `float8`      |             |
| `restricted_to_watch_warning` | `bool`        |             |
| `input_row_count`             | `int4`        | Nullable    |
| `output_row_count`            | `int4`        | Nullable    |
| `disturbance_count`           | `int4`        | Nullable    |
| `code_version`                | `varchar`     | Nullable    |
| `notes`                       | `text`        | Nullable    |
| `params`                      | `jsonb`       | Nullable    |

## Table `town`

### Columns

| Name         | Type          | Constraints |
| ------------ | ------------- | ----------- |
| `id`         | `int4`        | Primary     |
| `name`       | `varchar`     |             |
| `state`      | `varchar`     |             |
| `lat`        | `float8`      |             |
| `lon`        | `float8`      |             |
| `is_major`   | `bool`        |             |
| `is_island`  | `bool`        |             |
| `created_at` | `timestamptz` |             |

## Table `best_track_observation`

### Columns

| Name                             | Type          | Constraints |
| -------------------------------- | ------------- | ----------- |
| `id`                             | `int4`        | Primary     |
| `dataset`                        | `varchar`     |             |
| `disturbance_pk`                 | `int4`        |             |
| `tm`                             | `timestamptz` |             |
| `ingest_run_id`                  | `int4`        | Nullable    |
| `source_row_number`              | `int4`        | Nullable    |
| `type_code`                      | `varchar`     | Nullable    |
| `comment_text`                   | `varchar`     | Nullable    |
| `data_src`                       | `int4`        | Nullable    |
| `surface_code`                   | `int4`        | Nullable    |
| `cyc_type`                       | `int4`        | Nullable    |
| `lat`                            | `float8`      | Nullable    |
| `lon`                            | `float8`      | Nullable    |
| `position_method`                | `int4`        | Nullable    |
| `position_uncertainty`           | `int4`        | Nullable    |
| `dvorak_data_t_no`               | `float8`      | Nullable    |
| `dvorak_model_t_no`              | `float8`      | Nullable    |
| `dvorak_pattern_t_no`            | `float8`      | Nullable    |
| `dvorak_final_t_no`              | `float8`      | Nullable    |
| `dvorak_ci_no`                   | `float8`      | Nullable    |
| `central_pres`                   | `int4`        | Nullable    |
| `central_pres_uncertainty`       | `int4`        | Nullable    |
| `central_pres_method`            | `int4`        | Nullable    |
| `pres_wind_relation_used`        | `int4`        | Nullable    |
| `env_pres`                       | `int4`        | Nullable    |
| `env_pres_uncertainty`           | `int4`        | Nullable    |
| `mn_radius_outer_isobar`         | `int4`        | Nullable    |
| `mn_rad_out_isobar_uncertainty`  | `int4`        | Nullable    |
| `mn_radius_gf_wind`              | `int4`        | Nullable    |
| `mn_radius_gf_secne`             | `int4`        | Nullable    |
| `mn_radius_gf_secse`             | `int4`        | Nullable    |
| `mn_radius_gf_secsw`             | `int4`        | Nullable    |
| `mn_radius_gf_secnw`             | `int4`        | Nullable    |
| `mn_radius_sf_wind`              | `int4`        | Nullable    |
| `mn_radius_sf_secne`             | `int4`        | Nullable    |
| `mn_radius_sf_secse`             | `int4`        | Nullable    |
| `mn_radius_sf_secsw`             | `int4`        | Nullable    |
| `mn_radius_sf_secnw`             | `int4`        | Nullable    |
| `mn_radius_hf_wind`              | `int4`        | Nullable    |
| `mn_radius_hf_secne`             | `int4`        | Nullable    |
| `mn_radius_hf_secse`             | `int4`        | Nullable    |
| `mn_radius_hf_secsw`             | `int4`        | Nullable    |
| `mn_radius_hf_secnw`             | `int4`        | Nullable    |
| `mn_radius_max_wind`             | `int4`        | Nullable    |
| `mn_radius_max_wind_uncertainty` | `int4`        | Nullable    |
| `mn_radius_gf_wind_uncertainty`  | `int4`        | Nullable    |
| `mn_radius_sf_wind_uncertainty`  | `int4`        | Nullable    |
| `mn_radius_hf_wind_uncertainty`  | `int4`        | Nullable    |
| `mn_radius_max_wind_method`      | `int4`        | Nullable    |
| `mn_radius_gf_wind_method`       | `int4`        | Nullable    |
| `mn_radius_sf_wind_method`       | `int4`        | Nullable    |
| `mn_radius_hf_wind_method`       | `int4`        | Nullable    |
| `wind_spd_per`                   | `int4`        | Nullable    |
| `max_wind_spd`                   | `float8`      | Nullable    |
| `max_wind_spd_uncertainty`       | `float8`      | Nullable    |
| `max_wind_spd_method`            | `int4`        | Nullable    |
| `max_wind_gust_per`              | `int4`        | Nullable    |
| `max_wind_gust`                  | `float8`      | Nullable    |
| `max_wind_gust_method`           | `int4`        | Nullable    |
| `mn_eye_rad`                     | `float8`      | Nullable    |
| `mn_eye_rad_uncertainty`         | `int4`        | Nullable    |
| `mn_eye_rad_method`              | `int4`        | Nullable    |
| `max_rep_wind_spd`               | `float8`      | Nullable    |
| `max_rep_wind_dir`               | `int4`        | Nullable    |
| `max_rep_wind_method`            | `int4`        | Nullable    |
| `max_rep_wind_lon`               | `float8`      | Nullable    |
| `max_rep_wind_lat`               | `float8`      | Nullable    |
| `max_rep_wav_ht`                 | `float8`      | Nullable    |
| `max_rep_wav_method`             | `int4`        | Nullable    |
| `max_rep_wav_lon`                | `float8`      | Nullable    |
| `max_rep_wav_lat`                | `float8`      | Nullable    |
| `max_rep_swl_ht`                 | `float8`      | Nullable    |
| `max_rep_swl_dir`                | `int4`        | Nullable    |
| `max_rep_swl_per`                | `int4`        | Nullable    |
| `max_rep_swl_method`             | `int4`        | Nullable    |
| `max_rep_swl_lon`                | `float8`      | Nullable    |
| `max_rep_swl_lat`                | `float8`      | Nullable    |
| `max_rep_tide_anom`              | `float8`      | Nullable    |
| `max_rep_tide_anom_uncertainty`  | `float8`      | Nullable    |
| `max_rep_tide_anom_method`       | `int4`        | Nullable    |
| `max_rep_tide_anom_lon`          | `float8`      | Nullable    |
| `max_rep_tide_anom_lat`          | `float8`      | Nullable    |
| `otcr_adj_adt_vm_kn`             | `float8`      | Nullable    |
| `otcr_cp_ckz_hpa`                | `float8`      | Nullable    |
| `otcr_poci_lok_hpa`              | `float8`      | Nullable    |
| `otcr_vmax_kn`                   | `float8`      | Nullable    |
| `otcr_wind_gust_kn`              | `float8`      | Nullable    |
| `otcr_adjusted_vm`               | `float8`      | Nullable    |

## Table `bulletin`

### Columns

| Name             | Type          | Constraints |
| ---------------- | ------------- | ----------- |
| `id`             | `int4`        | Primary     |
| `disturbance_pk` | `int4`        |             |
| `region`         | `varchar`     |             |
| `source_file`    | `varchar`     | Unique      |
| `product_id`     | `varchar`     | Nullable    |
| `dist_name_raw`  | `varchar`     | Nullable    |
| `fcast_time`     | `timestamptz` | Nullable    |
| `issue_time`     | `timestamptz` | Nullable    |
| `expiry_hrs`     | `float8`      | Nullable    |
| `srs`            | `varchar`     |             |
| `bbox_min_lon`   | `float8`      | Nullable    |
| `bbox_min_lat`   | `float8`      | Nullable    |
| `bbox_max_lon`   | `float8`      | Nullable    |
| `bbox_max_lat`   | `float8`      | Nullable    |
| `content_hash`   | `varchar`     | Nullable    |
| `ingest_run_id`  | `int4`        | Nullable    |
| `created_at`     | `timestamptz` |             |

## Table `code_value`

### Columns

| Name          | Type      | Constraints |
| ------------- | --------- | ----------- |
| `id`          | `int4`    | Primary     |
| `domain_id`   | `int4`    |             |
| `code`        | `varchar` |             |
| `description` | `varchar` |             |
| `sort_order`  | `int4`    |             |

## Table `interpolated_point`

### Columns

| Name                   | Type          | Constraints |
| ---------------------- | ------------- | ----------- |
| `id`                   | `int4`        | Primary     |
| `run_id`               | `int4`        |             |
| `disturbance_pk`       | `int4`        |             |
| `tm`                   | `timestamptz` |             |
| `is_interpolated`      | `bool`        |             |
| `lat`                  | `float8`      | Nullable    |
| `lon`                  | `float8`      | Nullable    |
| `max_wind_spd`         | `float8`      | Nullable    |
| `position_uncertainty` | `float8`      | Nullable    |
| `mn_radius_gf_wind`    | `float8`      | Nullable    |
| `mn_radius_gf_secne`   | `float8`      | Nullable    |
| `mn_radius_gf_secse`   | `float8`      | Nullable    |
| `mn_radius_gf_secsw`   | `float8`      | Nullable    |
| `mn_radius_gf_secnw`   | `float8`      | Nullable    |
| `mn_radius_sf_wind`    | `float8`      | Nullable    |
| `mn_radius_sf_secne`   | `float8`      | Nullable    |
| `mn_radius_sf_secse`   | `float8`      | Nullable    |
| `mn_radius_sf_secsw`   | `float8`      | Nullable    |
| `mn_radius_sf_secnw`   | `float8`      | Nullable    |
| `mn_radius_hf_wind`    | `float8`      | Nullable    |
| `mn_radius_hf_secne`   | `float8`      | Nullable    |
| `mn_radius_hf_secse`   | `float8`      | Nullable    |
| `mn_radius_hf_secsw`   | `float8`      | Nullable    |
| `mn_radius_hf_secnw`   | `float8`      | Nullable    |

## Table `town_group_membership`

### Columns

| Name            | Type      | Constraints |
| --------------- | --------- | ----------- |
| `id`            | `int4`    | Primary     |
| `town_id`       | `int4`    |             |
| `town_group`    | `varchar` |             |
| `coastal_order` | `float8`  | Nullable    |

## Table `verification_run`

### Columns

| Name                   | Type          | Constraints |
| ---------------------- | ------------- | ----------- |
| `id`                   | `int4`        | Primary     |
| `created_at`           | `timestamptz` |             |
| `label`                | `varchar`     | Nullable    |
| `interpolation_run_id` | `int4`        | Nullable    |
| `forecast_source`      | `varchar`     | Nullable    |
| `truth_dataset`        | `varchar`     | Nullable    |
| `town_count`           | `int4`        | Nullable    |
| `disturbance_count`    | `int4`        | Nullable    |
| `base_time_step_hours` | `int4`        | Nullable    |
| `code_version`         | `varchar`     | Nullable    |
| `notes`                | `text`        | Nullable    |
| `params`               | `jsonb`       | Nullable    |

## Table `bulletin_area`

### Columns

| Name            | Type          | Constraints |
| --------------- | ------------- | ----------- |
| `id`            | `int4`        | Primary     |
| `bulletin_id`   | `int4`        |             |
| `kind`          | `varchar`     |             |
| `area_type`     | `varchar`     | Nullable    |
| `extent`        | `varchar`     | Nullable    |
| `wind_type`     | `varchar`     | Nullable    |
| `marine_type`   | `varchar`     | Nullable    |
| `fix_type`      | `varchar`     | Nullable    |
| `fix_time`      | `timestamptz` | Nullable    |
| `geometry`      | `jsonb`       |             |
| `polygon_count` | `int4`        |             |
| `ring_count`    | `int4`        |             |
| `vertex_count`  | `int4`        |             |
| `bbox_min_lon`  | `float8`      |             |
| `bbox_min_lat`  | `float8`      |             |
| `bbox_max_lon`  | `float8`      |             |
| `bbox_max_lat`  | `float8`      |             |

## Table `bulletin_fix`

### Columns

| Name                | Type          | Constraints |
| ------------------- | ------------- | ----------- |
| `id`                | `int4`        | Primary     |
| `bulletin_id`       | `int4`        |             |
| `fix_type`          | `varchar`     | Nullable    |
| `fix_time`          | `timestamptz` | Nullable    |
| `symbol`            | `varchar`     | Nullable    |
| `category`          | `int2`        | Nullable    |
| `time_offset_hours` | `float8`      | Nullable    |
| `lon`               | `float8`      |             |
| `lat`               | `float8`      |             |

## Table `bulletin_track`

### Columns

| Name           | Type          | Constraints |
| -------------- | ------------- | ----------- |
| `id`           | `int4`        | Primary     |
| `bulletin_id`  | `int4`        |             |
| `track_type`   | `varchar`     | Nullable    |
| `start_time`   | `timestamptz` | Nullable    |
| `end_time`     | `timestamptz` | Nullable    |
| `geometry`     | `jsonb`       |             |
| `vertex_count` | `int4`        |             |
| `bbox_min_lon` | `float8`      | Nullable    |
| `bbox_min_lat` | `float8`      | Nullable    |
| `bbox_max_lon` | `float8`      | Nullable    |
| `bbox_max_lat` | `float8`      | Nullable    |

## Table `verification_forecast_distance`

### Columns

| Name                     | Type          | Constraints |
| ------------------------ | ------------- | ----------- |
| `id`                     | `int4`        | Primary     |
| `run_id`                 | `int4`        |             |
| `disturbance_pk`         | `int4`        |             |
| `base_time`              | `timestamptz` |             |
| `town_id`                | `int4`        |             |
| `distance_to_watch_km`   | `float8`      | Nullable    |
| `distance_to_warning_km` | `float8`      | Nullable    |
| `watch`                  | `bool`        |             |
| `warning`                | `bool`        |             |

## Table `verification_observed_distance`

### Columns

| Name                       | Type          | Constraints |
| -------------------------- | ------------- | ----------- |
| `id`                       | `int4`        | Primary     |
| `run_id`                   | `int4`        |             |
| `disturbance_pk`           | `int4`        |             |
| `town_id`                  | `int4`        |             |
| `tm`                       | `timestamptz` |             |
| `analysis_uncertainty_km`  | `float8`      | Nullable    |
| `distance_to_gale_km`      | `float8`      | Nullable    |
| `distance_to_storm_km`     | `float8`      | Nullable    |
| `distance_to_hurricane_km` | `float8`      | Nullable    |

## Table `verification_observed_event`

### Columns

| Name             | Type          | Constraints |
| ---------------- | ------------- | ----------- |
| `id`             | `int4`        | Primary     |
| `run_id`         | `int4`        |             |
| `disturbance_pk` | `int4`        |             |
| `base_time`      | `timestamptz` |             |
| `town_id`        | `int4`        |             |
| `observed`       | `bool`        |             |

## Table `verification_pair`

### Columns

| Name             | Type          | Constraints |
| ---------------- | ------------- | ----------- |
| `id`             | `int4`        | Primary     |
| `run_id`         | `int4`        |             |
| `disturbance_pk` | `int4`        |             |
| `base_time`      | `timestamptz` |             |
| `town_id`        | `int4`        |             |
| `season`         | `varchar`     | Nullable    |
| `forecast`       | `bool`        |             |
| `observed`       | `bool`        |             |
| `outcome`        | `varchar`     |             |

## Table `verification_summary`

### Columns

| Name               | Type      | Constraints |
| ------------------ | --------- | ----------- |
| `id`               | `int4`    | Primary     |
| `run_id`           | `int4`    |             |
| `scope`            | `varchar` |             |
| `scope_key`        | `varchar` | Nullable    |
| `hit`              | `int4`    |             |
| `false_alarm`      | `int4`    |             |
| `miss`             | `int4`    |             |
| `correct_negative` | `int4`    |             |
| `total`            | `int4`    |             |
