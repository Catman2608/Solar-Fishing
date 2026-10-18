const APP_VERSION = "5.2";
const BETA_VERSION = "0";
const DEVELOPER = "Catman2608";
const validHexColor = /^#([0-9A-F]{3}|[0-9A-F]{6})$/i;

let currentConfig = "";
let applyingSettings = false;

window.addEventListener("pywebviewready", async () => {
    // Initialize controls before loading so config values and their previews
    // are applied once, in a deterministic order.
    if (document.readyState === "loading") {
        await new Promise((resolve) => {
            document.addEventListener("DOMContentLoaded", resolve, { once: true });
        });
    }
    // loadStartupConfig() -> loadSettings() refreshes the list before loading.
    await loadStartupConfig();
});

document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
        selectTab(button.dataset.tab);
    });
});

function _pyApi() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

async function closeWindow() {
    const api = _pyApi();
    if (!api || typeof api.close_window !== "function") {
        return;
    }
    await api.close_window();
}

async function minimizeWindow() {
    const api = _pyApi();
    if (!api || typeof api.minimize_window !== "function") {
        return;
    }
    await api.minimize_window();
}

async function rebindHotkeys(key) {
    const api = _pyApi();
    if (!api || typeof api.rebind_hotkeys !== "function") {
        return;
    }
    await api.rebind_hotkeys(key);
}

function applyHotkey(key, value) {
    const input = document.getElementById(key);
    const button = document.getElementById(key + "_btn");
    if (!input || !button) {
        return;
    }

    input.value = String(value);
    button.textContent = String(value).toUpperCase();
}

window.applyHotkey = applyHotkey;

function syncHotkeyButtons() {
    ["start_key", "area_selector_key", "stop_key"].forEach((key) => {
        const input = document.getElementById(key);
        if (input) {
            applyHotkey(key, input.value);
        }
    });
}

function setStatus(message) {
    const status = document.getElementById("status_label");

    if (!status) {
        return;
    }

    status.textContent = message;
}

function isRangeControl(element) {
    return Boolean(element) && (element.type === "range" || element.classList.contains("range-input"));
}

function syncSliderFromText(slider) {
    if (!slider) {
        return;
    }
    const textInput = document.getElementById(slider.dataset.target || "");
    if (!textInput) {
        return;
    }
    const value = parseFloat(textInput.value);
    if (Number.isNaN(value)) {
        return;
    }
    const min = parseFloat(slider.min);
    const max = parseFloat(slider.max);
    const clamped = Math.min(Math.max(value, min), max);
    slider.value = clamped;
}

function syncAllSliders() {
    document.querySelectorAll(".range-input").forEach(syncSliderFromText);
}

function setupSliders() {
    document.querySelectorAll(".range-input").forEach((slider) => {
        const targetId = slider.dataset.target;
        const textInput = document.getElementById(targetId);

        if (!textInput) {
            return;
        }

        // Slider → text
        slider.addEventListener("input", () => {
            textInput.value = slider.value;
        });

        // Text → slider
        textInput.addEventListener("input", () => {
            syncSliderFromText(slider);
        });

        syncSliderFromText(slider);
    });
}

function collectSettings() {
    const settings = {};

    document.querySelectorAll(
        "input[id], select[id], textarea[id]"
    ).forEach((element) => {
        if (!element.id || element.id === "config_list" || element.id.startsWith("_") || element.id.endsWith("_slider")) {
            return;
        }
        if (isRangeControl(element)) {
            return;
        }
        if (element.type === "checkbox") {
            settings[element.id] = element.checked;
        } else {
            settings[element.id] = element.value;
        }
    });

    return settings;
}

function isBlankSetting(value) {
    return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}

function settingIsChecked(value) {
    if (typeof value === "string") {
        return ["on", "true", "1", "yes"].includes(value.trim().toLowerCase());
    }
    return value === true || value === 1;
}

function fieldDefault(element) {
    if (!element) {
        return null;
    }
    if (element.type === "checkbox") {
        return Boolean(element.defaultChecked);
    }
    if (element.tagName === "SELECT") {
        const selected = element.querySelector("option[selected]");
        if (selected) {
            return selected.value;
        }
        if (element.options && element.options.length) {
            return element.options[0].value;
        }
        return "";
    }
    if (element.defaultValue !== undefined && String(element.defaultValue).trim() !== "") {
        return element.defaultValue;
    }
    if (element.placeholder && String(element.placeholder).trim() !== "") {
        return element.placeholder;
    }
    return null;
}

function fillBlankSettings(settings) {
    const filled = {};
    if (settings && typeof settings === "object") {
        Object.entries(settings).forEach(([key, value]) => {
            if (!key || key.startsWith("_") || key === "config_list") {
                return;
            }
            if (isBlankSetting(value)) {
                return;
            }
            filled[key] = value;
        });
    }

    document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
        const id = element.id;
        if (!id || id === "config_list" || id.startsWith("_") || id.endsWith("_slider") || isRangeControl(element)) {
            return;
        }
        if (!isBlankSetting(filled[id])) {
            return;
        }
        const fallback = fieldDefault(element);
        if (fallback === null || fallback === undefined) {
            return;
        }
        filled[id] = fallback;
    });

    return filled;
}

function selectedConfigName() {
    const select = document.getElementById("config_list");
    if (select && select.value) {
        return select.value;
    }
    return "Default";
}

async function refreshConfigs(preferred) {
    const api = _pyApi();
    const select = document.getElementById("config_list");
    if (!select) {
        return [];
    }
    if (!api || typeof api.list_configs !== "function") {
        return [];
    }

    let configs = [];
    try {
        configs = await api.list_configs();
    } catch (error) {
        configs = [];
    }
    if (!Array.isArray(configs)) {
        configs = [];
    }

    const current = preferred || select.value;
    select.innerHTML = "";
    configs.forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });

    if (current && configs.includes(current)) {
        select.value = current;
    } else if (configs.length) {
        select.value = configs[0];
    }

    return configs;
}

function collectSettingsData() {
    return fillBlankSettings(collectSettings());
}

async function saveSettings(configName) {
    const api = _pyApi();
    if (!api || typeof api.save_settings !== "function") {
        return;
    }

    const name = configName || currentConfig || selectedConfigName();
    await api.save_settings(name);
    if (!configName || configName === currentConfig || configName === selectedConfigName()) {
        currentConfig = name;
    }
}

function resetFieldsToDefaults() {
    document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
        if (!element.id || element.id === "config_list" || element.id.startsWith("_") || element.id.endsWith("_slider") || isRangeControl(element)) {
            return;
        }
        const fallback = fieldDefault(element);
        if (element.type === "checkbox") {
            element.checked = Boolean(fallback);
        } else if (fallback !== null && fallback !== undefined) {
            element.value = fallback;
        } else {
            element.value = "";
        }
        if (element.dataset.slider) {
            const slider = document.getElementById(element.dataset.slider);
            if (slider) {
                slider.value = element.value;
            }
        }
    });
}

function applySettings(settings, replace) {
    if (!settings || typeof settings !== "object") {
        return;
    }

    if (replace) {
        resetFieldsToDefaults();
    }

    Object.entries(settings).forEach(([id, value]) => {
        try {
            if (!id || id.startsWith("_") || id.endsWith("_slider") || id === "config_list") {
                return;
            }
            if (isBlankSetting(value)) {
                return;
            }

            const element = document.getElementById(id);

            if (!element || isRangeControl(element)) {
                return;
            }

            if (element.type === "checkbox") {
                element.checked = settingIsChecked(value);
            } else {
                element.value = value;
            }
        } catch (error) {
            // Skip a single setting that fails to load.
        }
    });

    syncAllSliders();

    applyingSettings = true;
    try {
        document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
            if (!element.id || element.id === "config_list" || element.id.startsWith("_")) {
                return;
            }
            element.dispatchEvent(new Event("change", { bubbles: true }));
        });
    } finally {
        applyingSettings = false;
    }

    syncHotkeyButtons();
    updateColorPreviews();
    updateAccentColor();
    if (typeof syncModeTabs === "function") {
        syncModeTabs(activeSidebarTab());
    }
}

let loadingConfig = false;

async function loadStartupConfig() {
    const api = _pyApi();
    let name = "";
    if (api && typeof api.get_last_config === "function") {
        try {
            name = await api.get_last_config();
        } catch (error) {
            name = "";
        }
    }
    await loadSettings(name || "");
}

let pendingConfig = "";

function unwrapSettings(loaded) {
    if (!loaded || typeof loaded !== "object") {
        return {};
    }
    if (loaded.settings && typeof loaded.settings === "object" && !Array.isArray(loaded.settings)) {
        return loaded.settings;
    }
    const copy = {};
    Object.entries(loaded).forEach(([key, value]) => {
        if (!key || key.startsWith("_") || key === "success" || key === "settings" || key === "config_name") {
            return;
        }
        copy[key] = value;
    });
    return copy;
}

function paintColorInput(input, raw) {
    if (!input) {
        return;
    }
    if (raw !== undefined && raw !== null && String(raw).trim() !== "") {
        input.value = String(raw).trim();
    }
    const value = normalizeHexColor(input.value || input.placeholder);
    if (!value) {
        return;
    }
    input.value = value.toUpperCase();
    input.style.setProperty("background", value, "important");
    input.style.setProperty("background-color", value, "important");
    input.style.color = hexBrightness(value) > 170 ? "#111827" : "#ffffff";
    input.style.border = "none";
}

function paintConfigColors(settings) {
    document.querySelectorAll("input.color-stripe, input[id$='_color']").forEach((input) => {
        const raw = settings && Object.prototype.hasOwnProperty.call(settings, input.id) ? settings[input.id] : undefined;
        paintColorInput(input, raw);
    });
}

const FISHING_TABS = ["cast", "shake", "minigame"];
const OTHER_TAB = "other_automation";

function selectTab(tabId) {
    document.querySelectorAll(".tab-button").forEach((btn) => {
        btn.classList.remove("active");
    });
    document.querySelectorAll(".tab-content").forEach((tab) => {
        tab.classList.remove("active");
    });

    const button = document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    const selectedTab = document.getElementById(tabId);
    if (button) {
        button.classList.add("active");
    }
    if (selectedTab) {
        selectedTab.classList.add("active");
    }
}

function activeSidebarTab() {
    const active = document.querySelector(".tab-button.active");
    return active && active.dataset.tab ? active.dataset.tab : "overview";
}

function tabAllowedForMode(tabId, fishing) {
    if (!tabId || !document.getElementById(tabId)) {
        return false;
    }
    const button = document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    if (button && button.hidden) {
        return false;
    }
    if (fishing && tabId === OTHER_TAB) {
        return false;
    }
    if (!fishing && FISHING_TABS.indexOf(tabId) !== -1) {
        return false;
    }
    return true;
}

function syncModeTabs(activeTab) {
    const modeSelect = document.getElementById("automation_mode");
    const fishing = !modeSelect || modeSelect.value === "fishing";

    FISHING_TABS.forEach((tabId) => {
        const button = document.querySelector('.tab-button[data-tab="' + tabId + '"]');
        if (button) button.hidden = !fishing;
    });
    const AutomationButton = document.querySelector('.tab-button[data-tab="' + OTHER_TAB + '"]');
    if (AutomationButton) AutomationButton.hidden = fishing;

    // Pick a fallback that is actually visible
    let target = activeTab;
    if (!tabAllowedForMode(target, fishing)) {
        target = fishing ? FISHING_TABS[0] : OTHER_TAB;
    }
    selectTab(target);
}

syncModeTabs(activeSidebarTab());

async function switchConfig(newConfigName) {
    if (!newConfigName) {
        return;
    }
    pendingConfig = newConfigName;
    if (loadingConfig) {
        return;
    }
    while (pendingConfig && pendingConfig !== currentConfig) {
        const next = pendingConfig;
        pendingConfig = "";
        const previous = currentConfig;
        if (previous && previous !== next) {
            await saveSettings(previous);
        }
        await loadSettings(next);
    }
}

async function loadSettings(configName) {
    if (loadingConfig) {
        return;
    }

    loadingConfig = true;
    const requested = configName;
    const api = _pyApi();
    let settings = {};

    try {
        let name = requested || "";

        if (!name && api && typeof api.get_last_config === "function") {
            try {
                name = await api.get_last_config();
            } catch (error) {
                name = "";
            }
        }

        try {
            await refreshConfigs(name);
        } catch (error) {
            // Keep going with whatever is already in the list.
        }

        name = name || selectedConfigName();

        if (api && typeof api.load_settings === "function") {
            try {
                const loaded = await api.load_settings(name);
                if (loaded && typeof loaded === "object") {
                    settings = loaded;
                    if (!settings._config_name && loaded.config_name) {
                        settings._config_name = loaded.config_name;
                    }
                }
            } catch (error) {
                settings = {};
            }
        }

        const select = document.getElementById("config_list");
        const loadedName = (settings && (settings._config_name || settings.config_name)) || name;
        const applied = unwrapSettings(settings);
        if (select && loadedName) {
            try {
                select.value = loadedName;
            } catch (error) {
                // Skip a bad config name.
            }
        }
        currentConfig = loadedName || selectedConfigName();

        applySettings(fillBlankSettings(applied), true);
        paintConfigColors(applied);
        if (currentConfig) {
            setStatus("Loaded: " + currentConfig);
        }
    } finally {
        loadingConfig = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    setupSliders();
    bindColorPreviewInputs();
    applySettings(fillBlankSettings({}));
    updateAccentColor();

    const refreshButton = document.getElementById("refresh-configs");
    if (refreshButton) {
        refreshButton.addEventListener("click", async () => {
            await refreshConfigs(selectedConfigName());
        });
    }
});

async function testLogging() {
    await pywebview.api.test_logging();
}

function normalizeHexColor(hex) {
    hex = String(hex || "").trim();
    if (/^[0-9A-F]{6}$/i.test(hex)) {
        hex = "#" + hex;
    }
    if (!validHexColor.test(hex)) {
        return "";
    }
    if (hex.length === 4) {
        hex = "#" + hex
            .slice(1)
            .split("")
            .map(char => char + char)
            .join("");
    }
    return hex;
}

function updateColorPreview(input) {
    paintColorInput(input);
}

function resetColor(id) {
    const input = document.getElementById(id);
    if (!input) {
        return;
    }
    input.value = input.placeholder || "";
    updateColorPreview(input);
    updateAccentColor();
}

async function pickColor(id) {
    const api = _pyApi();
    if (api && typeof api.start_eyedropper === "function") {
        try {
            await api.start_eyedropper(id);
            return;
        } catch (error) {
            // Fall through to the browser picker.
        }
    }
    const picker = document.createElement("input");
    picker.type = "color";
    const current = document.getElementById(id);
    const hex = normalizeHexColor(current && (current.value || current.placeholder));
    if (hex) {
        picker.value = hex;
    }
    picker.addEventListener("input", () => {
        if (!current) {
            return;
        }
        current.value = picker.value.toUpperCase();
        updateColorPreview(current);
        updateAccentColor();
    });
    picker.click();
}

function getColorPreviewInputs() {
    return document.querySelectorAll("input.color-stripe, input[id$='_color']");
}

function updateColorPreviews() {
    getColorPreviewInputs().forEach(updateColorPreview);
}

function bindColorPreviewInputs() {
    getColorPreviewInputs().forEach(input => {
        if (input.dataset.colorPreviewBound === "true") {
            return;
        }
        input.dataset.colorPreviewBound = "true";
        input.addEventListener("input", () => {
            updateColorPreview(input);
            if (!applyingSettings) updateAccentColor();
        });
        input.addEventListener("change", () => {
            updateColorPreview(input);
            if (!applyingSettings) updateAccentColor();
        });
        input.addEventListener("focus", () => updateColorPreview(input));
        updateColorPreview(input);
    });
}

function hexBrightness(hex) {
    hex = normalizeHexColor(hex);
    if (!hex) {
        return 0;
    }
    const r = parseInt(hex.substr(1,2), 16);
    const g = parseInt(hex.substr(3,2), 16);
    const b = parseInt(hex.substr(5,2), 16);
    return (
        0.2126 * r +
        0.7152 * g +
        0.0722 * b
    );
}

function updateAccentColor() {
    const leftElement = document.getElementById("bar_color");
    const rightElement = document.getElementById("right_color");
    const fishElement = document.getElementById("fish_color");
    
    // Safely get values
    const arrowElement = document.getElementById("arrow_color");
    const left = leftElement ? (leftElement.value || leftElement.placeholder || "").trim() : "";
    const right = rightElement ? (rightElement.value || rightElement.placeholder || "").trim() : "";
    const fish = fishElement ? (fishElement.value || fishElement.placeholder || "").trim() : "";
    const arrow = arrowElement ? (arrowElement.value || arrowElement.placeholder || "").trim() : "";
    
    // Normalize colors
    const normalizedLeft = normalizeHexColor(left);
    const normalizedRight = normalizeHexColor(right);
    const normalizedFish = normalizeHexColor(fish);
    const normalizedArrow = normalizeHexColor(arrow);
    
    // Helper: is a color too neutral (white/gray/black)?
    function isTooNeutral(hex) {
        if (!hex) return true;
        const brightness = hexBrightness(hex);
        const { r, g, b } = hexToRgb(hex);
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        const isGray = (max - min) < 30;
        const isWhite = brightness > 235;
        const isBlack = brightness < 15;
        return isWhite || isBlack || isGray;
    }
    
    const leftValid = !isTooNeutral(normalizedLeft);
    const rightValid = !isTooNeutral(normalizedRight);
    const fishValid = !isTooNeutral(normalizedFish);
    const arrowValid = !isTooNeutral(normalizedArrow);
    
    let leftGradient = "#fa6b35";
    let rightGradient = "#fa6b35";
    let accentColor = "#fa6b35"; // Always a valid hex color
    let isGradient = false;
    
    if (leftValid && rightValid) {
        // Both sides valid → gradient
        leftGradient = normalizedLeft;
        rightGradient = normalizedRight;
        accentColor = normalizedLeft; // Use left color for accent
        isGradient = true;
    } else if (leftValid) {
        // Only left valid → static
        leftGradient = normalizedLeft;
        rightGradient = normalizedLeft;
        accentColor = normalizedLeft;
    } else if (rightValid) {
        // Only right valid → static
        leftGradient = normalizedRight;
        rightGradient = normalizedRight;
        accentColor = normalizedRight;
    } else if (fishValid) {
        // Fallback to fish
        leftGradient = normalizedFish;
        rightGradient = normalizedFish;
        accentColor = normalizedFish;
    } else if (arrowValid) {
        leftGradient = normalizedArrow;
        rightGradient = normalizedArrow;
        accentColor = normalizedArrow;
    } else {
        // Ultimate fallback
        leftGradient = "#fa6b35";
        rightGradient = "#fa6b35";
        accentColor = "#fa6b35";
    }
    
    // Apply CSS variables
    document.documentElement.style.setProperty("--left-gradient", leftGradient);
    document.documentElement.style.setProperty("--right-gradient", rightGradient);
    document.documentElement.style.setProperty("--accent-color", accentColor);
    
    // Glow version – use left color if gradient, otherwise the static color
    const glowBase = isGradient ? normalizedLeft : accentColor;
    const r = parseInt(glowBase.substr(1,2), 16);
    const g = parseInt(glowBase.substr(3,2), 16);
    const b = parseInt(glowBase.substr(5,2), 16);
    document.documentElement.style.setProperty(
        "--accent-glow",
        `rgba(${r}, ${g}, ${b}, 0.4)`
    );
    document.documentElement.style.setProperty(
        "--focus-glow",
        `rgba(${r}, ${g}, ${b}, 0.28)`
    );
    document.documentElement.style.setProperty(
        "--focus-ring",
        `rgba(${r}, ${g}, ${b}, 0.75)`
    );
    document.documentElement.style.setProperty(
        "--border-soft",
        `rgba(${r}, ${g}, ${b}, 0.3)`
    );
    document.documentElement.style.setProperty(
        "--border-medium",
        `rgba(${r}, ${g}, ${b}, 0.25)`
    );
    document.documentElement.style.setProperty(
        "--border-strong",
        `rgba(${r}, ${g}, ${b}, 0.35)`
    );
    document.documentElement.style.setProperty("--scrollbar-thumb", accentColor);
    document.documentElement.style.setProperty(
        "--scrollbar-thumb-hover",
        rightGradient
    );
    
    // Update button text contrast
    updateButtonContrast();
}

function hexToRgb(hex) {
    hex = hex.replace("#", "");
    if (hex.length === 3) {
        hex = hex.split("").map(c => c + c).join("");
    }
    const num = parseInt(hex, 16);
    return {
        r: (num >> 16) & 255,
        g: (num >> 8) & 255,
        b: num & 255
    };
}
function getBrightness(hex) {
    const { r, g, b } = hexToRgb(hex);
    return (r * 299 + g * 587 + b * 114) / 1000;
}

function updateButtonContrast() {
    const left =
        getComputedStyle(document.documentElement)
        .getPropertyValue("--left-gradient")
        .trim();
    const right =
        getComputedStyle(document.documentElement)
        .getPropertyValue("--right-gradient")
        .trim();
    const leftBrightness = getBrightness(normalizeHexColor(left) || "#fa6b35");
    const rightBrightness = getBrightness(normalizeHexColor(right) || "#ff8a5c");
    const average = (leftBrightness + rightBrightness) / 2;
    const textColor = average > 170 ? "#111827" : "white";
    document.documentElement.style.setProperty("--button-text", textColor);
}

async function selectRatio(target) {
    const fieldId = target && target.id ? target.id : String(target || "");
    const api = _pyApi();
    if (!api || typeof api.select_ratio !== "function") {
        return;
    }
    try {
        await api.select_ratio(fieldId);
    } catch (error) {
        console.error(error);
    }
}


/* =========================
   BOTTOM BANNER
   ========================= */

function hideBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.add("hidden");
}

function showBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.remove("hidden");
}

function showUpdateBanner() {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const actions = document.getElementById("banner-actions");

    if (title) title.textContent = "Update Available";
    if (notice) notice.textContent = "A new version of Solar Fishing is available. Choose an option below.";
    if (dialogue) dialogue.classList.add("hidden");

    if (actions) {
        actions.innerHTML = `
            <button type="button" class="btn-ghost" onclick="hideBanner()">Skip this version</button>
            <button type="button" class="btn-secondary" onclick="hideBanner()">Remind me later</button>
            <button type="button" class="btn-primary" onclick="hideBanner()">Install update</button>
        `;
    }

    showBanner();
}

function showDialogueBanner() {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const input = document.getElementById("banner-input");
    const actions = document.getElementById("banner-actions");

    if (title) title.textContent = "Dialogue";
    if (notice) notice.textContent = "Enter a value and confirm.";
    if (dialogue) dialogue.classList.remove("hidden");
    if (input) {
        input.value = "";
        setTimeout(() => input.focus(), 50);
    }

    if (actions) {
        actions.innerHTML = `
            <button type="button" class="btn-ghost" onclick="hideBanner()">Cancel</button>
            <button type="button" class="btn-primary" onclick="confirmDialogue()">Confirm</button>
        `;
    }

    showBanner();
}

function confirmDialogue() {
    const input = document.getElementById("banner-input");
    const value = input ? input.value.trim() : "";
    // Placeholder — wire this to whatever action you need
    console.log("Dialogue confirmed with:", value);
    hideBanner();
}
