# Catatan

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Fenrir Framework](https://img.shields.io/badge/Fenrir%20Framework-4.4%2B-6366f1)](https://pypi.org/project/fenrir-framework/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Backblaze B2](https://img.shields.io/badge/Backblaze-B2-E21E25)](https://www.backblaze.com/b2)
[![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS%20%26%20CSS-F7DF1E?logo=javascript&logoColor=black)](#fitur-lengkap)
[![Deploy](https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white)](#deploy-ke-vercel)
[![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)](#pengujian)

**Tulis, simpan, dan bagikan catatan markdown** — aplikasi web penuh-fitur berbasis
[Fenrir Framework](https://pypi.org/project/fenrir-framework/) (Python ASGI), MongoDB, dan
Backblaze B2, dengan panel admin, pencarian, revisi, dan optimasi SEO/performa.

---

## Daftar Isi

- [Ringkasan](#ringkasan)
- [Fitur Lengkap](#fitur-lengkap)
- [Teknologi](#teknologi)
- [Struktur Proyek](#struktur-proyek)
- [Persyaratan](#persyaratan)
- [Instalasi & Menjalankan](#instalasi--menjalankan)
- [Konfigurasi Environment](#konfigurasi-environment)
- [Rute](#rute)
- [Arsitektur](#arsitektur)
- [Keamanan](#keamanan)
- [Performa](#performa)
- [Penyimpanan & Penghapusan Media](#penyimpanan--penghapusan-media)
- [Pengujian](#pengujian)
- [Deploy ke Vercel](#deploy-ke-vercel)
- [Lisensi](#lisensi)

---

## Ringkasan

Catatan adalah aplikasi catatan markdown satu-pengguna/tim kecil:

- **Publik**: beranda daftar catatan, halaman detail dengan pembaca markdown,
  daftar isi otomatis, tag, kategori, pencarian, feed RSS, sitemap, dan
  Open Graph image yang digenerate otomatis.
- **Admin**: login terlindungi rate-limit, editor markdown dengan toolbar,
  unggah gambar (tempel/seret), sampul catatan, kategori berwarna, riwayat
  revisi, dashboard, dan pengelolaan profil.
- **Penyimpanan**: MongoDB (Atlas atau lokal) untuk data,
  Backblaze B2 untuk media dengan fallback disk lokal.

## Fitur Lengkap

### Publik

- **Beranda** `/` — kartu catatan (sampul, badge sematan, waktu baca, jumlah
  tampilan), paginasi (9/halaman), pencarian `?q=`, filter `?kategori=` dan
  `?tag=`; catatan tersemat diurutkan pertama.
- **Halaman catatan** `/catatan/<slug>` — render markdown penuh (heading,
  kode dengan tombol salin, tabel, gambar, blockquote), **daftar isi otomatis
  (TOC) dari h2/h3 yang bisa dibuka/tutup** (state diingat di `localStorage`),
  scroll-spy penanda bagian aktif, waktu baca, jumlah kata, jumlah tampilan
  (dihitung async tanpa memblokir render), catatan terkait & catatan lainnya,
  bar bagikan (salin tautan, WhatsApp, X, Web Share API), tombol unduh `.md`,
  dan mode cetak.
- **Tag** `/tag` (indeks semua tag) dan `/tag/<slug>` — slug di-URL-encode
  sehingga tag berspasi (`basic os`) tetap bisa dibuka.
- **Kategori** `/kategori/<slug>` — halaman per kategori.
- **Pencarian** `/search` + API `/api/search?q=` (min. 2 karakter, maks. 8
  hasil) — pakai **indeks teks MongoDB `$text` dengan bobot**
  (judul 5, tag 3, ringkasan 2, isi 1) dan **fallback regex** (`re.escape`,
  case-insensitive) bila indeks teks tidak menemukan apa pun.
- **SEO & metadata** — JSON-LD `Article`, meta `og:`/`twitter:` lengkap,
  `sitemap.xml`, `robots.txt` (blokir `/admin` & `/api/`), dan **feed RSS**
  `/feed.xml`.
- **Open Graph image otomatis** `/og-image/<slug>` — kartu 1200×630
  (Pillow): judul + nama situs + strip warna aksen kategori. Dipakai
  otomatis sebagai `og:image` bila catatan **tidak punya sampul**. Hasil
  di-cache di `cache/og/` dengan ETag/304.
- **Mode gelap** — tombol tema (terang/gelap/otomatis) di header, state
  disimpan (`catatan-theme`), diinisialisasi *sebelum paint* oleh
  `theme-init.js` agar tidak berkedip.

### Editor & Admin (`/admin`, wajib login)

- **Dashboard** — ringkasan singkat (API `/admin/api/summary`).
- **CRUD catatan** — buat/edit/hapus, status draf–terbit, sematan, sampul,
  tag, kategori, ekspor `.md`.
- **Editor** — toolbar (tebal, miring, judul, tautan, gambar, kode, dll.),
  pratinjau langsung, **autosave draf ke `localStorage`**
  (`catatan-draft:<path>`), statistik kata/karakter/waktu baca.
- **Unggah gambar** — tempel (Ctrl+V), seret-lepas, atau tombol unggah;
  batas ukuran `MAX_UPLOAD_SIZE` (default 5MB).
- **Riwayat revisi** — setiap simpan menyimpan snapshot; **10 revisi
  terakhir** disimpan per catatan; bisa dipulihkan.
- **Kategori** — CRUD + warna aksen (dipakai strip gambar OG).
- **Profil & password** — ganti nama/password (bcrypt).
- **Hapus media sesi editor** — gambar yang diunggah lalu dihapus dari
  editor (bahkan sebelum disimpan) ikut terhapus dari penyimpanan
  (audit debounce 1,5 dtk + flush saat simpan/tutup tab, lihat
  [Penyimpanan & Penghapusan Media](#penyimpanan--penghapusan-media)).

### Keamanan & integritas data (ringkas — detail di bawah)

- Login: **rate-limit 5 percobaan/300 detik per IP** + log keputusan,
  password bcrypt (dengan *timing equalization*).
- CSRF (header `X-CSRF-Token` + cookie), sanitizer HTML *allowlist*
  (server: `nh3`; klien: parser ketat), CSP tanpa inline script.
- Cookie sesi: `HttpOnly`, `SameSite=Lax`, `Secure` **adaptif**
  (lihat [Keamanan](#keamanan)).

## Teknologi

| Lapisan | Teknologi |
|---|---|
| Bahasa | Python 3.14 (target ≥3.11) |
| Framework ASGI | [`fenrir-framework`](https://pypi.org/project/fenrir-framework/) ≥4.4 (rute, middleware, Jinja, session) |
| Basis data | MongoDB via `motor` (async) — Atlas/SRV atau lokal |
| Objek | Backblaze B2 (`b2sdk`) — bucket privat diproxy lewat aplikasi; fallback disk lokal |
| Gambar | Pillow (OG image, **validasi konten unggahan**) |
| Markdown/sanitasi | `markdown` + `nh3` (allowlist HTML) |
| Auth | `bcrypt` |
| Frontend | HTML/Jinja2 + CSS vanilla + JavaScript vanilla (tanpa framework/build step) |
| Format | `orjson` (JSON cepat), `python-multipart` |
| Deploy | Lokal (Asteri ASGI worker) atau Vercel (`@vercel/python`) |

## Struktur Proyek

```
catatan/
├── app.py                 # Bootstrap: middleware, blueprint, error handler
├── config.py              # Konfigurasi dari environment variables
├── database.py            # Koneksi Mongo, index, seed admin
├── template_helpers.py    # Helper render Jinja
├── requirements.txt       # Dependensi Python
├── vercel.json            # Konfigurasi deploy Vercel
├── .env.example           # Contoh konfigurasi environment
├── middleware/
│   ├── auth.py            # Guard sesi admin (kadaluarsa & pencabutan)
│   └── secure_cookie.py   # Penyesuaian atribut Secure cookie per konteks
├── models/
│   ├── note.py            # Catatan: CRUD, pencarian, revisi, views, terkait
│   ├── category.py        # Kategori
│   └── user.py            # Pengguna + autentikasi bcrypt
├── services/
│   ├── b2.py              # Upload/hapus/dl B2 + fallback lokal + validasi gambar
│   ├── og.py              # Generator kartu OG image (Pillow + resolver font)
│   └── sanitize.py        # Sanitizer HTML allowlist (nh3)
├── routes/
│   ├── public.py          # Beranda, catatan, tag, kategori, SEO, proxy B2
│   ├── auth.py            # Login/logout + rate limit + log
│   └── admin.py           # Panel admin (CRUD, media, kategori, profil)
├── templates/             # Template publik + templates/admin/
├── static/
│   ├── css/style.css      # Seluruh gaya (termasuk mode gelap)
│   ├── js/                # main.js, note-form.js, categories.js, theme-init.js, load-assets.js
│   ├── fonts/             # DejaVu Sans (untuk OG image)
│   └── favicon*           # Ikon situs
├── scripts/make_favicon.py  # Skrip pembuat varian favicon
└── favicon.ico
```

## Persyaratan

- Python **3.11+** (dikembangkan & diuji di Python 3.14)
- MongoDB — bisa [MongoDB Atlas](https://www.mongodb.com/atlas) (SRV) atau
  server lokal
- (Opsional) Akun & bucket **Backblaze B2** — tanpa ini semua media
  disimpan di `static/uploads/`
- Node.js hanya untuk pengembangan front-end/test (tidak wajib — tidak ada
  build step)

## Instalasi & Menjalankan

```bash
git clone <url-repositori> catatan
cd catatan

# Dependensi
pip install -r requirements.txt

# Konfigurasi
cp .env.example .env
# lalu edit .env — minimal: SECRET_KEY, MONGODB_URI, ADMIN_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # untuk SECRET_KEY

# Jalankan
python3 app.py
# → http://127.0.0.1:8000   (DEV_MODE=0)
# → http://0.0.0.0:8000     (DEV_MODE=1)
```

Catatan startup:

- **Index database dibuat otomatis** saat koneksi pertama (termasuk indeks
  teks `notes_text` berbobot dan indeks `note_revisions (note_id, saved_at)`).
- **Admin dibuat otomatis** dari `ADMIN_USERNAME`/`ADMIN_PASSWORD` bila belum
  ada; password di `.env` **direset ulang** ke nilai env setiap startup
  (ubah password lewat `/admin/profil` atau env).

## Konfigurasi Environment

Salin `.env.example` → `.env` (atau isi di dashboard Vercel). Semua variabel:

| Variabel | Wajib | Default | Keterangan |
|---|---|---|---|
| `SECRET_KEY` | ✅ | — | Kunci tanda-tangan sesi & CSRF (64 char acak) |
| `MONGODB_URI` | ✅ | — | String koneksi Mongo (SRV Atlas atau `mongodb://…`) |
| `MONGODB_DB_NAME` | — | `catatan` | Nama database |
| `ADMIN_USERNAME` | — | `admin` | Username admin (dibuat saat startup) |
| `ADMIN_PASSWORD` | ✅ | — | Password admin (direset tiap startup) |
| `ADMIN_NAME` | — | `Administrator` | Nama tampilan admin |
| `DEV_MODE` | — | `0` | `1` = mode dev (bind `0.0.0.0`, HSTS/docs/dev-cache) |
| `BASE_URL` | — | `http://localhost:8000` | URL asal — dipakai sitemap, OG, feed |
| `SITE_NAME` | — | `Catatan` | Nama situs |
| `SITE_TAGLINE` | — | `Tulis, simpan, dan bagikan catatan markdown` | Tagline |
| `B2_APPLICATION_KEY_ID` | — | — | Kunci B2 (kosongkan = penyimpanan lokal) |
| `B2_APPLICATION_KEY` | — | — | Rahasia kunci B2 |
| `B2_BUCKET_NAME` | — | `catatan` | Nama bucket |
| `B2_BUCKET_ID` | — | — | ID bucket (opsional) |
| `B2_ENDPOINT` | — | — | Endpoint B2 (opsional) |
| `MAX_UPLOAD_SIZE` | — | `5242880` (5MB) | Batas ukuran unggahan (byte) |
| `RATE_LIMIT_MAX` | — | `200` | Maks request global per jendela |
| `RATE_LIMIT_WINDOW` | — | `60` | Jendela rate limit global (detik) |
| `SESSION_COOKIE_SECURE` | — | `0` jika `DEV_MODE`, selainnya `1` | Atribut `Secure` cookie sesi (disesuaikan otomatis oleh middleware) |
| `NOTES_PER_PAGE` | — | `9` | Catatan per halaman publik |
| `ADMIN_NOTES_PER_PAGE` | — | `15` | Catatan per halaman admin |
| `PORT` | — | `8000` | Port (hanya saat `python3 app.py`) |

## Rute

### Publik

| Rute | Fungsi |
|---|---|
| `GET /` | Beranda (daftar, `?q=`, `?kategori=`, `?tag=`, paginasi) |
| `GET /catatan/<slug>` | Detail catatan (terbit saja) |
| `GET /catatan/<slug>/unduh` | Unduh sebagai `.md` |
| `GET /tag`, `GET /tag/<slug>` | Indeks tag / catatan per tag |
| `GET /kategori/<slug>` | Catatan per kategori |
| `GET /search` | Halaman hasil pencarian |
| `GET /api/search?q=` | JSON hasil pencarian (min. 2 char) |
| `GET /og-image/<slug>` | Gambar OG digenerate (cached + ETag) |
| `GET /api/b2/file/<file_id>` | Proxy gambar B2 (privat, validasi ID, ETag 1 hari) |
| `GET /sitemap.xml`, `/robots.txt`, `/feed.xml` | SEO & RSS |
| `GET /favicon.ico` | Favicon |

### Autentikasi

| Rute | Fungsi |
|---|---|
| `GET/POST /login` | Login (rate limit 5/300 dtk per IP, log keputusan) |
| `POST /logout` | Logout |

### Admin (wajib login + CSRF)

| Rute | Fungsi |
|---|---|
| `GET /admin/` | Dashboard |
| `GET/POST /admin/catatan/tambah` | Buat catatan |
| `GET/POST /admin/catatan/<id>/edit` | Edit catatan (membersihkan media yang tak terpakai) |
| `GET /admin/catatan/<id>/lihat` | Pratinjau draf |
| `POST /admin/catatan/<id>/hapus` | Hapus catatan (+ media tak terpakai) |
| `GET /admin/catatan/<id>/revisi` | Daftar revisi |
| `POST /admin/catatan/<id>/revisi/pulihkan` | Pulihkan revisi |
| `GET /admin/catatan` | Daftar semua catatan |
| `GET /admin/kategori` + `POST …/tambah|edit|hapus` | CRUD kategori |
| `POST /admin/upload` | Unggah gambar (divalidasi Pillow) |
| `POST /admin/media/hapus` | Hapus file media yang dirujuk (audit sesi editor) |
| `GET/POST /admin/profil`, `POST /admin/password` | Profil & password |
| `GET /admin/api/summary` | Ringkasan dashboard (JSON) |

## Arsitektur

**Middleware** (luar → dalam, lihat `app.py`):

1. `SecureCookieMiddleware` — selaraskan atribut `Secure` cookie
2. `BodyLimitMiddleware` — tolak body > 4× `MAX_UPLOAD_SIZE` (413)
3. `RateLimitMiddleware` — batas global per IP per menit
4. `SecurityHeadersMiddleware` — CSP, HSTS, XFO, dll.
5. `RequestIDMiddleware` — ID request untuk log
6. `CSRFMiddleware` — verifikasi `X-CSRF-Token`/`csrf_token`
7. `GZipMiddleware` — kompresi respons (HTML/JSON/CSS/JS, min. 500 byte)

**Alur permintaan**: route → cek DB siap (`ensure_ready` per request, reconnect
singkat) → guard auth/CSRF (admin) → handler → template Jinja / JSON.
Sesi disimpan sebagai **cookie bertanda tangan** (bukan koleksi DB).

**Render catatan**: markdown → HTML → sanitizer allowlist (server) →
di halaman, konten dirender ulang/disempurnakan oleh JS (highlight kode,
TOC, tombol salin) dengan sanitizer klien berlapis.

## Keamanan

- **Header**: `Content-Security-Policy` ketat (`script-src 'self'`,
  `frame-ancestors 'self'`, `object-src 'none'`, `form-action 'self'`),
  `Strict-Transport-Security` (1 tahun, produksi), `X-Frame-Options`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- **CSRF**: token per sesi — header `X-CSRF-Token` atau field `csrf_token`
  (untuk `sendBeacon`); cookie `_csrf_token` `SameSite=Lax`.
- **Login**: bcrypt + *dummy hash* (waktu respons seragam walau user tidak
  ada), rate limit **5 percobaan/300 detik/IP**, log `login berhasil/gagal`
  dan pemblokiran.
- **Sesi**: cookie `HttpOnly` + `SameSite=Lax`, kadaluarsa 7 hari, bisa
  dicabut (`revoke_user_sessions`), `SESSION_MAX_AGE=604800`.
- **Cookie `Secure` adaptif** (`middleware/secure_cookie.py`): diberikan saat
  HTTPS (langsung/`X-Forwarded-Proto`) atau host localhost; **dilepas** saat
  HTTP lewat IP non-localhost (mis. akses LAN) supaya login tetap jalan — di
  HTTP polos atribut itu tidak memberi proteksi transport apa pun.
- **XSS**: konten markdown melewati allowlist HTML (server `nh3` + parser
  ketat di klien); tidak ada inline handler/script (CSP aman).
- **Injection**: semua query Mongo memakai parameter terstruktur; pencarian
  regex memakai `re.escape`; urutan sort selalu nilai internal.
- **Unggah**: wajib login + CSRF, whitelist ekstensi (`.png .jpg .jpeg .gif
  .webp`), batas ukuran, nama file UUID acak, **validasi isi**: wajib gambar
  valid (Pillow `verify()`), format harus sesuai ekstensi, maks **40
  megapiksel** (anti *decompression bomb*).
- **B2**: bucket privat — URL asal tidak dipakai; semua diakses lewat proxy
  `/api/b2/file/<id>` dengan validasi pola ID.
- **Error**: halaman ramah tanpa membocorkan stack trace; `DEV_MODE=0`
  menonaktifkan docs/debug.
- **`robots.txt`**: melarang `/admin` dan `/api/`.

## Performa

- **Kompresi GZip** aktif untuk HTML/JSON/CSS/JS (contoh: beranda 7 KB →
  1,8 KB).
- **Indeks MongoDB**: `slug` (unique), `(status, published_at)`,
  `(status, is_pinned, published_at)`, `(category_id, status)`, `tags`,
  teks berbobot `notes_text`, dan `note_revisions (note_id, saved_at)`.
- **Proyeksi daftar** (`LIST_PROJECTION`) — `content` tidak dimuat untuk
  daftar kartu.
- **Cache**: static `max-age=3600`, proxy B2 `max-age=86400` + ETag/304,
  OG image cached + ETag/304.
- **Render responsif**: `views` dinaikkan lewat *fire-and-forget* task
  (respons tidak menunggu), gambar pertama `fetchpriority="high"`, gambar
  lain `loading="lazy"`.
- **Sanitizer & render**: `orjson` untuk JSON, agregasi Mongo ter-`limit`.

## Penyimpanan & Penghapusan Media

**Alur unggah** (`services/b2.py`): validasi (ukuran → ekstensi → isi
gambar) → upload ke B2 (folder `catatan/`, nama UUID) → URL
`/api/b2/file/<file_id>`. Jika B2 tidak terkonfigurasi/gagal, file jatuh ke
`static/uploads/` (persisten hanya untuk server dengan disk tulis).

**Pembersihan media** — file hanya dihapus bila **tidak dirujuk catatan
mana pun** (guard `refs` lintas-catatan):

- **Edit catatan** — gambar/sampul yang hilang dari konten & sampul baru
  dihapus setelah simpan (`cleanup_edit_media`).
- **Hapus catatan** — seluruh media yang menjadi milik catatan ikut
  dihapus bila tak terpakai tempat lain.
- **Sesi editor (tanpa simpan)** — URL unggahan selama sesi dicatat
  (`sessionUploads`); saat teks/sampul berubah, URL yang sudah tidak ada
  dikirim ke `POST /admin/media/hapus` (debounce 1,5 dtk; flush via
  `sendBeacon` saat simpan/tutup tab). Server mengecek login, CSRF, dan
  guard referensi — `note_id` catatan yang sedang diedit dikecualikan agar
  skenario "edit, hapus gambar, belum simpan" tetap terhapus dengan aman.

## Pengujian

Pengujian otomatis dijalankan sebagai skrip terpisah (belum ter-commit ke
repo) — status terakhir **semua lulus**:

| Suite | Cakupan | Hasil |
|---|---|---|
| `test_hl.js` | Highlight kode markdown | 27/27 |
| `test_md.js` | Renderer markdown + sanitizer | 25/25 |
| `test_editor.js` | Editor, unggah, autosave, audit media sesi | 25/25 |
| `test_toc.js` | TOC, scroll-spy, buka/tutup + persistensi | 20/20 |
| `test_media_purge.py` | E2E endpoint `/admin/media/hapus` | 14/14 |
| `test_media_cleanup.py` | E2E cleanup saat edit/hapus/purge | 23/23 |
| `test_hardening.py` | Index revisi, cookie Secure adaptif, validasi upload | 9/9 |

## Deploy ke Vercel

`vercel.json` sudah tersedia (build `app.py` dengan `@vercel/python`, semua
rute ke fungsi Python). Langkahnya:

1. Push repo ke GitHub (`.env` sudah dikecualikan `.gitignore`).
2. Import repo di vercel.com — **set environment variables dulu**
   (`SECRET_KEY` wajib; tanpa itu import `app.py` gagal saat build).
3. `npx vercel --prod`.

Hal yang perlu disesuaikan untuk serverless:

- **`MAX_UPLOAD_SIZE=4000000`** — Vercel membatasi body request 4,5 MB.
- **Filesystem baca-saja** (kecuali `/tmp`): cache `cache/og/` dan fallback
  upload lokal tidak persisten; pastikan **B2 aktif** di Vercel.
- Task *background* (kenaikan `views`) bisa gugur setelah respons — views
  mungkin kurang akurat di serverless.
- Rate limit & pencatat login in-memory (reset tiap *cold start*).
- Static dilayani lewat fungsi; untuk trafik besar, pertimbangkan memindah
  aset ke `public/` agar disajikan Vercel secara langsung.

## Lisensi

MIT — lihat [LICENSE](LICENSE).
