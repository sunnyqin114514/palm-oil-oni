/**
 * 前后端共享的数据契约 (API contract) 类型定义。
 * 与 backend/app/main.py 的 SeriesResponse 完全对齐，保证字段名 100% 一致。
 */

export interface SeriesRow {
  date: string;
  close: number;
}

export interface SeriesMeta {
  rows: number;
  start: string;
  end: string;
  missing_close: number;
}

export interface SeriesResponse {
  symbol: string;
  source: string;
  freq: string;
  rows: SeriesRow[];
  meta: SeriesMeta;
}

export interface HelloResponse {
  status: string;
  service: string;
  version: string;
  message: string;
}

export interface Point3D {
  x: number;
  y: number;
  z: number;
  t: number;
  label: string;
}
