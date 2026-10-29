/**
 * stats.raupulus.dev — Cliente Público Read-Only (/ws/public)
 * Seguridad DOM estricta: 100% document.createElement + textContent.
 */

(() => {
  "use strict";

  const ALL_PROFILES_ID = "__all__";
  const SOCIAL_PLATFORMS_ORDER = [
    "youtube",
    "twitch",
    "github",
    "gitlab",
    "twitter",
    "instagram",
    "telegram",
    "tiktok",
    "facebook",
    "mastodon",
    "bluesky",
    "linkedin",
  ];

  const PLATFORM_METADATA = {
    youtube: { code: "YT", name: "YouTube", followersLabel: "Suscriptores", postsLabel: "Vídeos" },
    twitch: { code: "TWCH", name: "Twitch", followersLabel: "Seguidores", postsLabel: "Vídeos / VODs" },
    github: { code: "GH", name: "GitHub", followersLabel: "Seguidores", postsLabel: "Repositorios" },
    gitlab: { code: "GL", name: "GitLab", followersLabel: "Seguidores", postsLabel: "Proyectos" },
    twitter: { code: "X", name: "X / Twitter", followersLabel: "Seguidores", postsLabel: "Publicaciones" },
    instagram: { code: "IG", name: "Instagram", followersLabel: "Seguidores", postsLabel: "Publicaciones" },
    telegram: { code: "TG", name: "Telegram", followersLabel: "Suscriptores Canal", postsLabel: "Mensajes" },
    tiktok: { code: "TT", name: "TikTok", followersLabel: "Seguidores", postsLabel: "Vídeos" },
    facebook: { code: "FB", name: "Facebook", followersLabel: "Seguidores", postsLabel: "Publicaciones" },
    mastodon: { code: "MSTD", name: "Mastodon", followersLabel: "Seguidores", postsLabel: "Toots" },
    bluesky: { code: "BSKY", name: "Bluesky", followersLabel: "Seguidores", postsLabel: "Posts" },
    linkedin: { code: "IN", name: "LinkedIn", followersLabel: "Seguidores", postsLabel: "Publicaciones" },
    crypto: { code: "SPOT", name: "Crypto Spot" },
    keycounter: { code: "KEY", name: "Keycounter" },
  };

  const numberFormatter = new Intl.NumberFormat("es-ES");
  const usdFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
  const eurFormatter = new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });

  const state = {
    profiles: {},
    selectedProfileIds: new Set(),
    initializedProfiles: false,
    selectedCategory: "all",
    eventsCount: 0,
    recentUpdates: [],
    flashedCardKey: "",
    flashTimer: null,
    ws: null,
    reconnectAttempt: 0,
    reconnectTimer: null,
  };

  function el(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function formatInt(val) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return "—";
    }
    return numberFormatter.format(Math.round(Number(val)));
  }

  function formatSignedDelta(val, prefix = "") {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return `${prefix}0`;
    }
    const num = Math.round(Number(val));
    const sign = num >= 0 ? "+" : "";
    return `${prefix}${sign}${numberFormatter.format(num)}`;
  }

  function formatCurrency(val, currency) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return "—";
    }
    const num = Number(val);
    if (currency === "EUR") {
      return eurFormatter.format(num);
    }
    return usdFormatter.format(num);
  }

  function formatPct(val) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return "0.00%";
    }
    const num = Number(val);
    const sign = num >= 0 ? "+" : "";
    return `${sign}${num.toFixed(2)}%`;
  }

  function formatUptime(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const d = Math.floor(total / 86400);
    const h = Math.floor((total % 86400) / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (d > 0) {
      return `${d}d ${h}h ${m}m`;
    }
    if (h > 0) {
      return `${h}h ${m}m ${s}s`;
    }
    return `${m}m ${s}s`;
  }

  function updateSyncClock(isoTimestamp) {
    const clockNode = document.getElementById("last-sync-time");
    if (!clockNode) {
      return;
    }
    const dateObj = isoTimestamp ? new Date(isoTimestamp) : new Date();
    if (Number.isNaN(dateObj.getTime())) {
      clockNode.textContent = "--:--:-- UTC";
      return;
    }
    const hh = String(dateObj.getUTCHours()).padStart(2, "0");
    const mm = String(dateObj.getUTCMinutes()).padStart(2, "0");
    const ss = String(dateObj.getUTCSeconds()).padStart(2, "0");
    clockNode.textContent = `${hh}:${mm}:${ss} UTC`;
  }

  function setWsConnectionStatus(mode, labelText) {
    const pill = document.getElementById("ws-status-pill");
    const textNode = document.getElementById("ws-status-text");
    if (!pill || !textNode) {
      return;
    }
    pill.classList.remove("is-connected", "is-connecting", "is-disconnected");
    if (mode === "connected") {
      pill.classList.add("is-connected");
    } else if (mode === "disconnected") {
      pill.classList.add("is-disconnected");
    } else {
      pill.classList.add("is-connecting");
    }
    textNode.textContent = labelText;
  }

  function applyDeltaClass(badgeNode, value) {
    badgeNode.classList.remove("is-positive", "is-negative", "is-neutral");
    const num = Number(value);
    if (!Number.isFinite(num) || num === 0) {
      badgeNode.classList.add("is-neutral");
    } else if (num > 0) {
      badgeNode.classList.add("is-positive");
    } else {
      badgeNode.classList.add("is-negative");
    }
  }

  function syncSelectedProfilesWithState() {
    const allIds = Object.keys(state.profiles);
    if (allIds.length === 0) {
      return;
    }
    for (const id of Array.from(state.selectedProfileIds)) {
      if (!state.profiles[id]) {
        state.selectedProfileIds.delete(id);
      }
    }
    if (!state.initializedProfiles || state.selectedProfileIds.size === 0) {
      for (const id of allIds) {
        state.selectedProfileIds.add(id);
      }
      state.initializedProfiles = true;
    }
  }

  function getActiveProfilesList() {
    syncSelectedProfilesWithState();
    const allIds = Object.keys(state.profiles);
    const active = allIds
      .filter((pid) => state.selectedProfileIds.has(pid))
      .map((pid) => state.profiles[pid]);
    return active.length > 0 ? active : allIds.map((pid) => state.profiles[pid]);
  }

  function countProfileAccounts(profileObj) {
    if (!profileObj || !profileObj.platforms) {
      return 0;
    }
    let count = 0;
    for (const platKey of Object.keys(profileObj.platforms)) {
      const summary = profileObj.platforms[platKey];
      if (summary && Array.isArray(summary.accounts)) {
        count += summary.accounts.length;
      }
    }
    return count;
  }

  function renderProfileSelectorCards() {
    const grid = document.getElementById("profiles-selector-grid");
    const contextLabel = document.getElementById("active-context-label");
    if (!grid) {
      return;
    }

    syncSelectedProfilesWithState();
    const profileIds = Object.keys(state.profiles);
    const cards = [];

    if (profileIds.length === 0) {
      cards.push(
        buildProfileSelectorCard({
          profileId: ALL_PROFILES_ID,
          initials: "GL",
          name: "Todos los Perfiles (Global)",
          description: "Sincronizando perfiles públicos desde /ws/public…",
          accountsCount: 0,
          slugText: "conectando…",
          isActive: true,
        })
      );
    } else {
      for (const pid of profileIds) {
        const prof = state.profiles[pid];
        const initials =
          (prof.name || pid)
            .replace(/[^a-zA-Z0-9]/g, "")
            .slice(0, 2)
            .toUpperCase() || "PR";
        const isActive = state.selectedProfileIds.has(pid);
        cards.push(
          buildProfileSelectorCard({
            profileId: pid,
            initials,
            name: prof.name || pid,
            description:
              prof.description || "Perfil público monitorizado en tiempo real",
            accountsCount: countProfileAccounts(prof),
            slugText: `@${pid}`,
            isActive,
          })
        );
      }
    }

    grid.replaceChildren(...cards);

    if (contextLabel) {
      const activeNames = profileIds
        .filter((pid) => state.selectedProfileIds.has(pid))
        .map((pid) => state.profiles[pid].name || pid);
      if (activeNames.length === 0) {
        contextLabel.textContent = "Todos los perfiles (Global)";
      } else {
        contextLabel.textContent = activeNames.join(" + ");
      }
    }
  }

  function buildProfileSelectorCard({
    profileId,
    initials,
    name,
    description,
    accountsCount,
    slugText,
    isActive,
  }) {
    const btn = el(
      "button",
      `profile-selector-card${isActive ? " is-active" : ""}`
    );
    btn.type = "button";
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    btn.dataset.profileId = profileId;

    const topRow = el("div", "profile-card-top");
    const identity = el("div", "profile-identity");
    const avatar = el("span", "profile-avatar", initials);
    const textWrap = el("div", "");
    const titleNode = el("div", "profile-name", name);
    const descNode = el("div", "profile-desc", description);
    textWrap.append(titleNode, descNode);
    identity.append(avatar, textWrap);

    const countPill = el(
      "span",
      "profile-count-pill",
      `${accountsCount} cuentas`
    );
    topRow.append(identity, countPill);

    const bottomRow = el("div", "profile-card-bottom");
    const slugNode = el("code", "profile-slug-code", slugText);
    const activeBadge = el(
      "span",
      "profile-active-badge",
      isActive ? "✓ ACTIVO" : "OCULTO · ACTIVAR"
    );
    bottomRow.append(slugNode, activeBadge);

    btn.append(topRow, bottomRow);
    btn.addEventListener("click", () => {
      if (profileId === ALL_PROFILES_ID) {
        return;
      }
      const allIds = Object.keys(state.profiles);
      if (state.selectedProfileIds.has(profileId)) {
        if (state.selectedProfileIds.size > 1) {
          state.selectedProfileIds.delete(profileId);
        } else {
          for (const id of allIds) {
            state.selectedProfileIds.add(id);
          }
        }
      } else {
        state.selectedProfileIds.add(profileId);
      }
      renderAll();
    });

    return btn;
  }

  function collectDeduplicatedAccountsByPlatform(profilesList) {
    const byPlatform = {};
    for (const prof of profilesList) {
      if (!prof || !prof.platforms) continue;
      for (const [plat, summary] of Object.entries(prof.platforms)) {
        if (!byPlatform[plat]) {
          byPlatform[plat] = new Map();
        }
        for (const acc of summary.accounts || []) {
          if (!byPlatform[plat].has(acc.account_key)) {
            byPlatform[plat].set(acc.account_key, acc);
          }
        }
      }
    }
    return byPlatform;
  }

  function renderSocialSection(activeProfiles, byPlatform) {
    const grid = document.getElementById("social-platforms-grid");
    const activeCountNode = document.getElementById("active-social-count");
    const kpiFollowers = document.getElementById("kpi-total-followers");
    const kpiDeltaFollowers = document.getElementById("kpi-delta-followers");
    const kpiStars = document.getElementById("kpi-total-stars");
    const kpiForks = document.getElementById("kpi-total-forks");
    const kpiViews = document.getElementById("kpi-total-views");
    const kpiDeltaViews24h = document.getElementById("kpi-delta-views-24h");
    const kpiPosts = document.getElementById("kpi-total-posts");
    const kpiDeltaViews1h = document.getElementById("kpi-delta-views-1h");

    if (!grid) return;

    let grandFollowers = 0;
    let grandFollowers24h = 0;
    let grandStars = 0;
    let grandForks = 0;
    let grandViews = 0;
    let grandViews24h = 0;
    let grandViews1h = 0;
    let grandPosts = 0;
    let activeSocialPlatforms = 0;

    for (const platKey of SOCIAL_PLATFORMS_ORDER) {
      const accMap = byPlatform[platKey];
      if (!accMap || accMap.size === 0) {
        continue;
      }
      activeSocialPlatforms += 1;
      for (const acc of accMap.values()) {
        const m = acc.metrics || {};
        grandFollowers += Number(m.followers_total || 0);
        grandFollowers24h += Number(m.followers_last_24h || 0);
        grandPosts += Number(m.posts_total || 0);
        if (m.stars_total !== null && m.stars_total !== undefined) {
          grandStars += Number(m.stars_total);
        }
        if (m.forks_total !== null && m.forks_total !== undefined) {
          grandForks += Number(m.forks_total);
        }
        if (m.views_total !== null && m.views_total !== undefined) {
          grandViews += Number(m.views_total);
        }
        if (m.views_last_24h !== null && m.views_last_24h !== undefined) {
          grandViews24h += Number(m.views_last_24h);
        }
        if (m.views_last_1h !== null && m.views_last_1h !== undefined) {
          grandViews1h += Number(m.views_last_1h);
        }
      }
    }

    if (activeCountNode) {
      activeCountNode.textContent = String(activeSocialPlatforms);
    }
    if (kpiFollowers) {
      kpiFollowers.textContent = formatInt(grandFollowers);
    }
    if (kpiDeltaFollowers) {
      kpiDeltaFollowers.textContent = formatSignedDelta(grandFollowers24h, "24h: ");
      applyDeltaClass(kpiDeltaFollowers, grandFollowers24h);
    }
    if (kpiStars) {
      kpiStars.textContent = formatInt(grandStars);
    }
    if (kpiForks) {
      kpiForks.textContent = `Forks: ${formatInt(grandForks)}`;
      kpiForks.classList.remove("is-positive", "is-negative", "is-neutral");
      kpiForks.classList.add(grandForks > 0 ? "is-positive" : "is-neutral");
    }
    if (kpiViews) {
      kpiViews.textContent = formatInt(grandViews);
    }
    if (kpiDeltaViews24h) {
      kpiDeltaViews24h.textContent = formatSignedDelta(grandViews24h, "24h: ");
      applyDeltaClass(kpiDeltaViews24h, grandViews24h);
    }
    if (kpiPosts) {
      kpiPosts.textContent = formatInt(grandPosts);
    }
    if (kpiDeltaViews1h) {
      kpiDeltaViews1h.textContent = formatSignedDelta(grandViews1h, "Vistas 1h: ");
      applyDeltaClass(kpiDeltaViews1h, grandViews1h);
    }

    const groupNodes = [];
    for (const prof of activeProfiles) {
      if (!prof || !prof.platforms) continue;
      const pid = prof.profile_id || prof.name || "perfil";
      const profileCards = [];
      let profFollowers = 0;
      let profStars = 0;
      let profViews = 0;
      let profPosts = 0;

      for (const platKey of SOCIAL_PLATFORMS_ORDER) {
        const summary = prof.platforms[platKey];
        if (!summary || !Array.isArray(summary.accounts) || summary.accounts.length === 0) {
          continue;
        }
        const accounts = summary.accounts;
        let platFollowers = 0;
        let platFollowers24h = 0;
        let platPosts = 0;
        let platStars = null;
        let platForks = null;
        let platIsLive = false;
        let platLiveViewers = 0;
        let platViews = null;
        let platViews24h = null;
        let platViews1h = null;
        let latestPostObj = null;
        let hasStale = false;

        for (const acc of accounts) {
          const m = acc.metrics || {};
          platFollowers += Number(m.followers_total || 0);
          platFollowers24h += Number(m.followers_last_24h || 0);
          platPosts += Number(m.posts_total || 0);
          if (m.stars_total !== null && m.stars_total !== undefined) {
            platStars = (platStars || 0) + Number(m.stars_total);
          }
          if (m.forks_total !== null && m.forks_total !== undefined) {
            platForks = (platForks || 0) + Number(m.forks_total);
          }
          if (m.is_live === true) {
            platIsLive = true;
          }
          if (m.live_viewers !== null && m.live_viewers !== undefined) {
            platLiveViewers += Number(m.live_viewers);
          }
          if (m.views_total !== null && m.views_total !== undefined) {
            platViews = (platViews || 0) + Number(m.views_total);
          }
          if (m.views_last_24h !== null && m.views_last_24h !== undefined) {
            platViews24h = (platViews24h || 0) + Number(m.views_last_24h);
          }
          if (m.views_last_1h !== null && m.views_last_1h !== undefined) {
            platViews1h = (platViews1h || 0) + Number(m.views_last_1h);
          }
          if (!latestPostObj && m.latest_post) {
            latestPostObj = m.latest_post;
          }
          if (acc.status && acc.status !== "healthy") {
            hasStale = true;
          }
        }

        profFollowers += platFollowers;
        profPosts += platPosts;
        if (platStars !== null) {
          profStars += platStars;
        }
        if (platViews !== null) {
          profViews += platViews;
        }

        profileCards.push(
          buildSocialPlatformCard({
            profileId: pid,
            platKey,
            accounts,
            platFollowers,
            platFollowers24h,
            platPosts,
            platStars,
            platForks,
            platIsLive,
            platLiveViewers,
            platViews,
            platViews24h,
            platViews1h,
            latestPostObj,
            hasStale,
          })
        );
      }

      if (profileCards.length === 0) {
        continue;
      }

      const groupBox = el("section", "profile-social-group");
      groupBox.dataset.profileId = pid;

      const groupHeader = el("div", "profile-group-header");
      const titleWrap = el("div", "");
      titleWrap.append(el("h3", "profile-group-title", prof.name || pid));

      const subtitleLine = el("p", "profile-group-subtitle");
      subtitleLine.append(
        document.createTextNode("Seguidores: "),
        el("strong", "", formatInt(profFollowers)),
        document.createTextNode(" · Estrellas/Likes: "),
        el("strong", "", `★ ${formatInt(profStars)}`),
        document.createTextNode(" · Vistas: "),
        el("strong", "", formatInt(profViews)),
        document.createTextNode(" · Publicaciones/Repos: "),
        el("strong", "", formatInt(profPosts))
      );
      titleWrap.append(subtitleLine);

      const groupPill = el(
        "span",
        "profile-group-pill",
        `@${pid} · ${profileCards.length} ${profileCards.length === 1 ? "plataforma" : "plataformas"}`
      );
      groupHeader.append(titleWrap, groupPill);

      const innerGrid = el("div", "profile-group-platforms-grid");
      innerGrid.append(...profileCards);

      groupBox.append(groupHeader, innerGrid);
      groupNodes.push(groupBox);
    }

    if (groupNodes.length === 0) {
      grid.replaceChildren(
        el(
          "div",
          "empty-state-box",
          "No hay cuentas de redes sociales activas en el perfil seleccionado."
        )
      );
    } else {
      grid.replaceChildren(...groupNodes);
    }
  }

  function buildSocialPlatformCard({
    profileId,
    platKey,
    accounts,
    platFollowers,
    platFollowers24h,
    platPosts,
    platStars,
    platForks,
    platIsLive,
    platLiveViewers,
    platViews,
    platViews24h,
    platViews1h,
    latestPostObj,
    hasStale,
  }) {
    const meta = PLATFORM_METADATA[platKey] || {
      code: platKey.slice(0, 3).toUpperCase(),
      name: platKey,
      followersLabel: "Seguidores / Suscriptores",
      postsLabel: "Publicaciones",
    };

    const isFlashed = state.flashedCardKey === `${profileId}:${platKey}`;
    const card = el("article", `platform-card${isFlashed ? " is-flash" : ""}`);
    card.dataset.platform = platKey;
    card.dataset.profileId = profileId;

    const header = el("header", "platform-card-header");
    const titleGroup = el("div", "platform-title-group");
    titleGroup.append(
      el("span", "platform-badge-code", meta.code),
      el("h3", "platform-name", meta.name)
    );

    let pillClass = "platform-status-pill";
    let pillText = `${accounts.length} ${accounts.length === 1 ? "CANAL" : "CANALES"}`;
    if (hasStale) {
      pillClass += " is-stale";
      pillText = "CACHÉ / STALE";
    } else if (platKey === "twitch" && platIsLive) {
      pillClass += " is-live-stream";
      pillText = `● EN DIRECTO · ${formatInt(platLiveViewers)}`;
    } else if (platKey === "twitch") {
      pillClass += " is-offline";
      pillText = "OFFLINE";
    }
    const statusPill = el("span", pillClass, pillText);
    header.append(titleGroup, statusPill);

    const contentRegion = el("div", "platform-card-content");
    const mainMetric = el("div", "platform-main-metric");
    const leftFollowers = el("div", "");
    leftFollowers.append(
      el("div", "platform-followers-value", formatInt(platFollowers)),
      el("div", "platform-followers-label", meta.followersLabel || "Seguidores / Suscriptores")
    );
    const deltaBadge = el(
      "span",
      "delta-badge",
      formatSignedDelta(platFollowers24h, "24h: ")
    );
    applyDeltaClass(deltaBadge, platFollowers24h);
    mainMetric.append(leftFollowers, deltaBadge);

    const subGrid = el("div", "platform-submetrics-grid");
    if (platKey === "github" || platKey === "gitlab") {
      const topRepoStars =
        latestPostObj && latestPostObj.likes !== null && latestPostObj.likes !== undefined
          ? `★ ${formatInt(latestPostObj.likes)}`
          : "—";
      subGrid.append(
        buildSubmetricCell(meta.postsLabel || "Repositorios", formatInt(platPosts)),
        buildSubmetricCell("Estrellas Totales", `★ ${formatInt(platStars || 0)}`),
        buildSubmetricCell("Forks Totales", formatInt(platForks || 0)),
        buildSubmetricCell("Último Repo Activo", topRepoStars)
      );
    } else if (platKey === "twitch") {
      const vodViews =
        latestPostObj && latestPostObj.views !== null && latestPostObj.views !== undefined
          ? formatInt(latestPostObj.views)
          : "—";
      subGrid.append(
        buildSubmetricCell("Estado Stream", platIsLive ? "EN DIRECTO" : "Offline"),
        buildSubmetricCell("Espectadores Live", platIsLive ? formatInt(platLiveViewers) : "0"),
        buildSubmetricCell(meta.postsLabel || "Vídeos / VODs", formatInt(platPosts)),
        buildSubmetricCell("Vistas Último VOD", vodViews)
      );
    } else if (platKey === "telegram") {
      const latestViews =
        latestPostObj && latestPostObj.views !== null && latestPostObj.views !== undefined
          ? formatInt(latestPostObj.views)
          : platViews !== null
            ? formatInt(platViews)
            : "—";
      subGrid.append(
        buildSubmetricCell("Último Mensaje", platPosts > 0 ? `#${formatInt(platPosts)}` : "—"),
        buildSubmetricCell("Vistas Último Post", latestViews),
        buildSubmetricCell(
          "Vistas 24h",
          platViews24h !== null ? formatSignedDelta(platViews24h) : "0"
        ),
        buildSubmetricCell(
          "Vistas 1h",
          platViews1h !== null ? formatSignedDelta(platViews1h) : "0"
        )
      );
    } else if (platKey === "facebook") {
      subGrid.append(
        buildSubmetricCell(
          "Me gusta Página",
          platStars !== null ? formatInt(platStars) : "N/A"
        ),
        buildSubmetricCell("Seguidores 24h", formatSignedDelta(platFollowers24h)),
        buildSubmetricCell(
          "Publicaciones",
          platPosts > 0 ? formatInt(platPosts) : "N/A"
        ),
        buildSubmetricCell("Canal", `${accounts.length} página`)
      );
    } else {
      subGrid.append(
        buildSubmetricCell(meta.postsLabel || "Publicaciones", formatInt(platPosts)),
        buildSubmetricCell(
          "Vistas Totales",
          platViews !== null ? formatInt(platViews) : "N/A"
        ),
        buildSubmetricCell(
          "Vistas 24h",
          platViews24h !== null ? formatSignedDelta(platViews24h) : "N/A"
        ),
        buildSubmetricCell(
          "Vistas 1h",
          platViews1h !== null ? formatSignedDelta(platViews1h) : "N/A"
        )
      );
    }

    contentRegion.append(mainMetric, subGrid);

    const accountsList = el("footer", "platform-accounts-list");
    for (const acc of accounts) {
      const row = el("div", "account-row");
      const labelGroup = el("div", "account-label-group");
      const rawHandle = acc.handle ? String(acc.handle).replace(/^@/, "") : acc.account_key;
      const handleDisplay =
        platKey === "gitlab" && acc.instance
          ? `@${rawHandle} · ${acc.instance}`
          : platKey === "telegram"
            ? `t.me/${rawHandle}`
            : `@${rawHandle}`;
      labelGroup.append(
        el("span", "account-title", acc.label || acc.handle || acc.account_key),
        el("span", "account-handle", handleDisplay)
      );
      const m = acc.metrics || {};
      let pillMetricText = `${formatInt(m.followers_total)} seg.`;
      if ((platKey === "github" || platKey === "gitlab") && m.stars_total !== null && m.stars_total !== undefined) {
        pillMetricText = `${formatInt(m.followers_total)} seg. · ★ ${formatInt(m.stars_total)}`;
      } else if (platKey === "telegram") {
        pillMetricText = `${formatInt(m.followers_total)} susc.`;
      } else if (platKey === "twitch" && m.is_live) {
        pillMetricText = `LIVE · ${formatInt(m.live_viewers)} esp.`;
      }
      const metricPill = el("code", "account-metric-pill", pillMetricText);
      row.append(labelGroup, metricPill);
      accountsList.append(row);
    }

    card.append(header, contentRegion, accountsList);
    return card;
  }

  function buildSubmetricCell(label, valText) {
    const cell = el("div", "submetric-cell");
    cell.append(
      el("span", "submetric-label", label),
      el("strong", "submetric-val", valText)
    );
    return cell;
  }

  function renderCryptoSection(byPlatform) {
    const grid = document.getElementById("crypto-spot-grid");
    if (!grid) return;

    const cryptoMap = byPlatform.crypto;
    if (!cryptoMap || cryptoMap.size === 0) {
      grid.replaceChildren(
        el(
          "div",
          "empty-state-box",
          "Sin activos cripto configurados en el ámbito seleccionado."
        )
      );
      return;
    }

    const cards = [];
    for (const acc of cryptoMap.values()) {
      const m = acc.metrics || {};
      const symbol = String(acc.handle || acc.account_key || "").toUpperCase();
      const card = el("article", "crypto-card");

      const header = el("div", "platform-card-header");
      const titleGroup = el("div", "platform-title-group");
      titleGroup.append(
        el("span", "platform-badge-code", symbol),
        el("h3", "platform-name", acc.label || symbol)
      );

      const pctUsd = m.price_change_24h_pct;
      const pctBadge = el("span", "delta-badge", `24h: ${formatPct(pctUsd)}`);
      applyDeltaClass(pctBadge, pctUsd);
      header.append(titleGroup, pctBadge);

      const pairBox = el("div", "crypto-prices-pair");

      const usdBox = el("div", "crypto-fiat-box");
      usdBox.append(
        el("span", "crypto-fiat-label", "COTIZACIÓN SPOT USD ($)"),
        el("strong", "crypto-fiat-price", formatCurrency(m.price_usd, "USD")),
        el(
          "span",
          "crypto-fiat-sub",
          `Máx: ${formatCurrency(m.high_24h_usd, "USD")} · Mín: ${formatCurrency(m.low_24h_usd, "USD")}`
        )
      );

      const eurBox = el("div", "crypto-fiat-box");
      eurBox.append(
        el("span", "crypto-fiat-label", "COTIZACIÓN SPOT EUR (€)"),
        el("strong", "crypto-fiat-price", formatCurrency(m.price_eur, "EUR")),
        el(
          "span",
          "crypto-fiat-sub",
          `Máx: ${formatCurrency(m.high_24h_eur, "EUR")} · Mín: ${formatCurrency(m.low_24h_eur, "EUR")}`
        )
      );

      pairBox.append(usdBox, eurBox);
      card.append(header, pairBox);
      cards.push(card);
    }

    grid.replaceChildren(...cards);
  }

  function renderKeycounterSection(byPlatform) {
    const pulsationsNode = document.getElementById("kc-pulsations-total");
    const clicksNode = document.getElementById("kc-clicks-total");
    const accountPill = document.getElementById("kc-account-pill");
    const statusPill = document.getElementById("kc-status-pill");

    const kcMap = byPlatform.keycounter;
    if (!kcMap || kcMap.size === 0) {
      if (pulsationsNode) pulsationsNode.textContent = "—";
      if (clicksNode) clicksNode.textContent = "—";
      if (statusPill) statusPill.textContent = "SIN CUENTA EN PERFIL";
      return;
    }

    let totalPulsations = 0;
    let totalClicks = 0;
    let firstHandle = "";

    for (const acc of kcMap.values()) {
      const m = acc.metrics || {};
      totalPulsations += Number(m.pulsations_total || 0);
      totalClicks += Number(m.clicks_total || 0);
      if (!firstHandle) {
        firstHandle = acc.handle || acc.account_key || "raupulus";
      }
    }

    if (pulsationsNode) {
      pulsationsNode.textContent = formatInt(totalPulsations);
    }
    if (clicksNode) {
      clicksNode.textContent = formatInt(totalClicks);
    }
    if (accountPill && firstHandle) {
      accountPill.textContent = `@${String(firstHandle).replace(/^@/, "")}`;
    }
    if (statusPill) {
      statusPill.textContent = "ACUMULADO HISTÓRICO";
    }
  }

  function renderCategoryVisibility() {
    const secSocial = document.getElementById("section-social");
    const secCrypto = document.getElementById("section-crypto");
    const secKc = document.getElementById("section-keycounter");

    const cat = state.selectedCategory;
    if (secSocial) {
      secSocial.classList.toggle("is-hidden", cat !== "all" && cat !== "social");
    }
    if (secCrypto) {
      secCrypto.classList.toggle("is-hidden", cat !== "all" && cat !== "crypto");
    }
    if (secKc) {
      secKc.classList.toggle("is-hidden", cat !== "all" && cat !== "keycounter");
    }

    const buttons = document.querySelectorAll(".filter-pill[data-category]");
    for (const btn of buttons) {
      const isSelected = btn.getAttribute("data-category") === cat;
      btn.classList.toggle("is-active", isSelected);
      btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
    }
  }

  function renderTelemetrySpecRow() {
    const counterNode = document.getElementById("ws-events-counter");
    if (counterNode) {
      counterNode.textContent = formatInt(state.eventsCount);
    }

    const pillsWrap = document.getElementById("live-events-pills");
    if (!pillsWrap) return;

    if (state.recentUpdates.length === 0) {
      pillsWrap.replaceChildren(
        el("code", "spec-code-pill", "Snapshot inicial cargado · escuchando cambios")
      );
      return;
    }

    const nodes = state.recentUpdates.map((item) =>
      el("code", "spec-code-pill", item)
    );
    pillsWrap.replaceChildren(...nodes);
  }

  function renderAll() {
    renderCategoryVisibility();
    renderProfileSelectorCards();
    const activeProfiles = getActiveProfilesList();
    const byPlatform = collectDeduplicatedAccountsByPlatform(activeProfiles);
    renderSocialSection(activeProfiles, byPlatform);
    renderCryptoSection(byPlatform);
    renderKeycounterSection(byPlatform);
    renderTelemetrySpecRow();
  }

  function applyMetricUpdateToState(data) {
    if (!data || !data.profile_id || !data.platform) {
      return;
    }
    const pid = data.profile_id;
    const plat = data.platform;
    if (!state.profiles[pid]) {
      state.profiles[pid] = {
        profile_id: pid,
        name: pid,
        description: "",
        platforms: {},
      };
      state.selectedProfileIds.add(pid);
    }
    if (data.platform_summary) {
      const prevSummary = state.profiles[pid].platforms[plat];
      const prevAccounts =
        prevSummary && Array.isArray(prevSummary.accounts)
          ? prevSummary.accounts
          : [];
      const incomingAccounts = Array.isArray(data.platform_summary.accounts)
        ? data.platform_summary.accounts
        : [];
      let mergedAccounts = incomingAccounts;
      if (mergedAccounts.length === 0 && prevAccounts.length > 0) {
        mergedAccounts = prevAccounts.slice();
      }
      if (data.account && data.account.account_key) {
        const idx = mergedAccounts.findIndex(
          (a) => a && a.account_key === data.account.account_key
        );
        if (idx >= 0) {
          mergedAccounts[idx] = data.account;
        } else {
          mergedAccounts.push(data.account);
        }
      }
      state.profiles[pid].platforms[plat] = {
        ...data.platform_summary,
        accounts: mergedAccounts,
      };
    }

    state.flashedCardKey = `${pid}:${plat}`;
    if (state.flashTimer) {
      clearTimeout(state.flashTimer);
    }
    state.flashTimer = window.setTimeout(() => {
      state.flashedCardKey = "";
      state.flashTimer = null;
      const flashedNodes = document.querySelectorAll(".platform-card.is-flash");
      for (const node of flashedNodes) {
        node.classList.remove("is-flash");
      }
    }, 1200);

    const changes = data.changes || {};
    const changedKeys = Object.keys(changes);
    if (changedKeys.length > 0) {
      const firstKey = changedKeys[0];
      const deltaObj = changes[firstKey];
      let changeLabel = "0";
      if (deltaObj && deltaObj.delta !== undefined && deltaObj.delta !== null) {
        const sign = Number(deltaObj.delta) >= 0 ? "+" : "";
        changeLabel = `${sign}${deltaObj.delta}`;
      } else if (deltaObj && typeof deltaObj.current === "boolean") {
        changeLabel = deltaObj.current ? "LIVE" : "OFFLINE";
      }
      const summaryText = `${plat}:${data.account_key} ${firstKey} (${changeLabel})`;
      state.recentUpdates.unshift(summaryText);
      if (state.recentUpdates.length > 4) {
        state.recentUpdates.pop();
      }
    }
  }

  function buildWsUrl() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/public`;
  }

  function connectWebSocket() {
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }

    setWsConnectionStatus("connecting", "CONECTANDO STREAM…");

    let socket;
    try {
      socket = new WebSocket(buildWsUrl());
    } catch {
      scheduleReconnect();
      return;
    }
    state.ws = socket;

    socket.addEventListener("open", () => {
      state.reconnectAttempt = 0;
      setWsConnectionStatus("connected", "STREAM EN VIVO · /ws/public");
    });

    socket.addEventListener("message", (event) => {
      let envelope;
      try {
        envelope = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!envelope || typeof envelope !== "object") {
        return;
      }

      state.eventsCount += 1;
      updateSyncClock(envelope.timestamp);

      const lastEventTypeNode = document.getElementById("spec-last-event-type");
      if (lastEventTypeNode && envelope.event) {
        lastEventTypeNode.textContent = String(envelope.event);
      }

      if (envelope.event === "snapshot" && envelope.data) {
        if (envelope.data.profiles && typeof envelope.data.profiles === "object") {
          state.profiles = envelope.data.profiles;
        } else if (envelope.data.profile_id) {
          state.profiles = { [envelope.data.profile_id]: envelope.data };
        }
        renderAll();
      } else if (envelope.event === "metric_update" && envelope.data) {
        applyMetricUpdateToState(envelope.data);
        renderAll();
      } else if (envelope.event === "heartbeat" && envelope.data) {
        const uptimeNode = document.getElementById("spec-server-uptime");
        if (uptimeNode && envelope.data.uptime_seconds !== undefined) {
          uptimeNode.textContent = `Uptime: ${formatUptime(envelope.data.uptime_seconds)}`;
        }
        renderTelemetrySpecRow();
      }
    });

    socket.addEventListener("close", () => {
      setWsConnectionStatus("disconnected", "RECONECTANDO STREAM…");
      scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) {
      return;
    }
    const baseDelay = Math.min(30000, 1000 * Math.pow(2, state.reconnectAttempt));
    state.reconnectAttempt += 1;
    state.reconnectTimer = window.setTimeout(() => {
      state.reconnectTimer = null;
      connectWebSocket();
    }, baseDelay);
  }

  function bindCategoryFilters() {
    const buttons = document.querySelectorAll(".filter-pill[data-category]");
    for (const btn of buttons) {
      btn.addEventListener("click", () => {
        const cat = btn.getAttribute("data-category") || "all";
        state.selectedCategory = cat;
        renderCategoryVisibility();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindCategoryFilters();
    renderAll();
    connectWebSocket();
  });
})();
