# Gus Explains branding

Channel art rendered by the cartoon engine (`node studio/branding.js`, scene layouts in `studio/engine/branding.html`).
The YouTube and Facebook APIs can't change a channel's name, handle or picture, so you apply these by hand.

| File | Size | Where it goes |
|---|---|---|
| `youtube_avatar.png` | 800×800 | YouTube profile picture (shown as a circle, down to 98 px) |
| `youtube_banner.png` | 2560×1440 | YouTube banner (text and characters sit inside the centred 1546×423 area that every device shows) |
| `facebook_profile.png` | 720×720 | Facebook Page profile picture |
| `facebook_cover.png` | 1640×624 | Facebook Page cover photo (key art inside the centred 1200×462 area that phones show) |
| `channel_description.txt` | 592 chars | YouTube channel description (limit 1,000) and the Facebook Page "About" text |

Regenerate after a look change: `npm ci && npx playwright install chromium`, then `node studio/branding.js`
(`--only avatar,banner,fb_profile,cover` for some; `--safe <dir>` also writes copies with the safe area drawn on).

## YouTube (studio.youtube.com, signed in as the channel)

YouTube allows **2 name changes and 2 handle changes in 14 days**, so pick the handle first and make the name change once.

1. Check the handle: open `https://www.youtube.com/@GusExplains` in a private window. A "This page isn't available"
   page means it's probably free. If it's taken, try `@GusExplainsIt`, then `@GusExplainsShorts`.
2. YouTube Studio → left menu **Customization** → tab **Profile**:
   - **Name**: click the pencil next to the name → `Gus Explains`.
   - **Handle**: click the pencil next to the handle → the handle from step 1 (a green tick means it's available).
   - **Description**: paste `channel_description.txt`.
   - **Picture**: **Change** → choose `youtube_avatar.png` → **Done** (keep the default crop).
   - **Banner image**: **Change** → choose `youtube_banner.png` → check the TV / desktop / mobile preview: the
     lettering and the four characters must be inside the smallest box → **Done**.
3. Click **Publish** (top right). The name and picture can take a few minutes to show everywhere.
4. Old crypto links: Customization → **Home tab** (or Layout): remove any featured crypto sections or trailer. Channel
   links (Profile → Links) that point to crypto pages: delete them.

## Facebook Page (facebook.com, switched into the Page)

1. Switch into the Page: your profile picture (top right) → **See all profiles** → the Page.
2. **Profile picture**: on the Page, click the camera icon on the profile picture → **Upload photo** →
   `facebook_profile.png` → **Save**.
3. **Cover photo**: **Edit cover photo** (bottom right of the cover) → **Upload photo** → `facebook_cover.png` →
   leave it centred → **Save changes**.
4. **Name**: Page menu → **Settings & privacy** → **Settings** → **Page setup** → **Name** → **Edit** →
   `Gus Explains` → **Review change** → **Request change**. Facebook reviews name changes (it can take a few days,
   and a big topic change may be refused; if so, the old name stays and the videos still post).
5. **Username**: **Settings** → **Page setup** → **Username** → **Edit** → `GusExplains` (or the same fallback as
   YouTube) → **Save**.
6. **About / bio**: on the Page, **Intro** → **Edit bio** → `Odd facts, explained with cartoons. Two new Reels every
   day.` → **Save**. Then **Edit details** (or **About** tab → **Edit**) → description = `channel_description.txt`,
   category = **Education** (or **Entertainment website**) → **Save**.

Facebook moves these menus now and then; if a step doesn't match, search the Page settings for "Name",
"Username", "Bio" or "Category".
