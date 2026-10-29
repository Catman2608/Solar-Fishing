const APP_VERSION = "5.2";
const BETA_VERSION = "0";
const DEVELOPER = "Catman2608";

// Expose for Python version check via evaluate_js
window.APP_VERSION = APP_VERSION;
window.BETA_VERSION = BETA_VERSION;
window.DEVELOPER = DEVELOPER;

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


async function detectRoblox() {
    const api = _pyApi();
    if (!api || typeof api.detect_roblox !== "function") {
        setStatus("Detect Roblox not available");
        return;
    }
    try {
        const info = await api.detect_roblox();
        if (info && typeof info.left !== "undefined") {
            setStatus(`Roblox: left=${info.left}, top=${info.top}, width=${info.width}, height=${info.height}`);
        }
    } catch (e) {
        setStatus("Error detecting Roblox window");
        console.error(e);
    }
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

        ensureAllColorGroups(applied);
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
    initColorGroups();
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

const COLOR_GROUPS = {
    bar: {
        label: "Bar",
        baseColorId: "bar_color",
        baseTolId: "bar_tolerance",
        containerId: "bar-colors-container",
        countId: "bar_color_count",
        defaultColor: "#F1F1F1",
        defaultTolerance: "8"
    },
    arrow: {
        label: "Arrow",
        baseColorId: "arrow_color",
        baseTolId: "arrow_tolerance",
        containerId: "arrow-colors-container",
        countId: "arrow_color_count",
        defaultColor: "#848587",
        defaultTolerance: "8"
    },
    fish: {
        label: "Fish",
        baseColorId: "fish_color",
        baseTolId: "fish_tolerance",
        containerId: "fish-colors-container",
        countId: "fish_color_count",
        defaultColor: "#434B5B",
        defaultTolerance: "4"
    },
    pinion_notes: {
        label: "Pinion Note",
        baseColorId: "pinion_notes_color",
        baseTolId: "pinion_notes_tolerance",
        containerId: "pinion_notes-colors-container",
        countId: "pinion_notes_color_count",
        defaultColor: "#149604",
        defaultTolerance: "4"
    },
    friends: {
        label: "Friend Area",
        baseColorId: "friends_color",
        baseTolId: "friends_tolerance",
        containerId: "friends-colors-container",
        countId: "friends_color_count",
        defaultColor: "#9BFF9B",
        defaultTolerance: "4"
    },
    green_cast: {
        label: "Green Cast",
        baseColorId: "green_cast_color",
        baseTolId: "green_cast_tolerance",
        containerId: "green_cast-colors-container",
        countId: "green_cast_color_count",
        defaultColor: "#64a04c",
        defaultTolerance: "16"
    },
    white_cast: {
        label: "White Cast",
        baseColorId: "white_cast_color",
        baseTolId: "white_cast_tolerance",
        containerId: "white_cast-colors-container",
        countId: "white_cast_color_count",
        defaultColor: "#d4d3ca",
        defaultTolerance: "20"
    },
    shake: {
        label: "Shake",
        baseColorId: "shake_color",
        baseTolId: "shake_tolerance",
        containerId: "shake-colors-container",
        countId: "shake_color_count",
        defaultColor: "#FFFFFF",
        defaultTolerance: "5"
    },
    sovereign_recharge: {
        label: "Sovereign Recharge",
        baseColorId: "sovereign_recharge_color",
        baseTolId: "sovereign_recharge_tolerance",
        containerId: "sovereign_recharge-colors-container",
        countId: "sovereign_recharge_color_count",
        defaultColor: "#d994ff",
        defaultTolerance: "5"
    }
};

function getColorGroupById(id) {
    if (!id) return null;
    for (const key of Object.keys(COLOR_GROUPS)) {
        const group = COLOR_GROUPS[key];
        if (id === group.baseColorId || id.startsWith(group.baseColorId + "_")) {
            return { key, group };
        }
    }
    return null;
}

function getColorId(group, index) {
    return index === 1 ? group.baseColorId : `${group.baseColorId}_${index}`;
}

function getTolId(group, index) {
    return index === 1 ? group.baseTolId : `${group.baseTolId}_${index}`;
}

async function addColor(id) {
    const found = getColorGroupById(id);
    if (!found) return;
    const { group } = found;
    const container = document.getElementById(group.containerId);
    if (!container) return;

    const currentCount = container.querySelectorAll(".color-option").length;
    const newIndex = currentCount + 1;
    const newOption = createColorOption(group, newIndex);
    container.appendChild(newOption);
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
    updateColorPreviews();
}

async function removeColor(id) {
    const found = getColorGroupById(id);
    if (!found) return;
    const { group } = found;
    const container = document.getElementById(group.containerId);
    if (!container) return;

    const options = container.querySelectorAll(".color-option");
    if (options.length <= 1) {
        return;
    }

    const input = document.getElementById(id);
    if (!input) return;
    const option = input.closest(".color-option");
    if (option) {
        option.remove();
    }

    reindexColors(group);
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
    updateColorPreviews();
}

function createColorOption(group, index) {
    const div = document.createElement("div");
    div.className = "color-option";
    div.dataset.index = index;

    const colorId = getColorId(group, index);
    const tolId = getTolId(group, index);

    div.innerHTML = `
        <p>${group.label}</p>
        <input id="${colorId}" class="color-stripe" type="text" placeholder="${group.defaultColor}" spellcheck="false">
        <p>Tolerance</p>
        <input id="${tolId}" class="tolerance-input" type="number" placeholder="${group.defaultTolerance}">
        <button class="color-icon-btn" type="button" onclick="pickColor('${colorId}')" title="Pick color" aria-label="Pick color">
            <svg class="icon" aria-hidden="true"><use href="#i-picker"></use></svg>
        </button>
        <button class="color-icon-btn" type="button" onclick="resetColor('${colorId}')" title="Reset color" aria-label="Reset color">
            <svg class="icon" aria-hidden="true"><use href="#i-reset"></use></svg>
        </button>
        <button class="color-icon-btn add-color-btn" type="button" onclick="addColor('${colorId}')" title="Add color" aria-label="Add color" style="display: none;">
            <svg class="icon" aria-hidden="true"><use href="#i-add"></use></svg>
        </button>
        <button class="color-icon-btn remove-color-btn" type="button" onclick="removeColor('${colorId}')" title="Remove color" aria-label="Remove color">
            <svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg>
        </button>
    `;
    return div;
}

function reindexColors(group) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    const options = Array.from(container.querySelectorAll(".color-option"));
    options.forEach((option, i) => {
        const index = i + 1;
        option.dataset.index = index;
        const colorInput = option.querySelector(".color-stripe");
        const tolInput = option.querySelector(".tolerance-input");
        const buttons = option.querySelectorAll(".color-icon-btn");

        const colorId = getColorId(group, index);
        const tolId = getTolId(group, index);

        if (colorInput) {
            colorInput.id = colorId;
        }
        if (tolInput) {
            tolInput.id = tolId;
        }

        if (buttons.length >= 4) {
            buttons[0].setAttribute("onclick", `pickColor('${colorId}')`);
            buttons[1].setAttribute("onclick", `resetColor('${colorId}')`);
            buttons[2].setAttribute("onclick", `addColor('${colorId}')`);
            buttons[3].setAttribute("onclick", `removeColor('${colorId}')`);
        }
    });
}

function updateColorCount(group) {
    const container = document.getElementById(group.containerId);
    const countInput = document.getElementById(group.countId);
    if (container && countInput) {
        const count = container.querySelectorAll(".color-option").length;
        countInput.value = String(count);
    }
}

function updateColorButtons(group) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    const options = container.querySelectorAll(".color-option");
    const single = options.length <= 1;
    options.forEach((option, i) => {
        const addBtn = option.querySelector(".add-color-btn");
        if (addBtn) {
            addBtn.style.display = (i === options.length - 1) ? "" : "none";
        }
        // Hide delete when there is only one color — it does nothing.
        const removeBtn = option.querySelector(".remove-color-btn")
            || option.querySelector("button[onclick^='removeColor']");
        if (removeBtn) {
            removeBtn.style.display = single ? "none" : "";
        }
    });
}

function ensureColorGroup(group, count) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    count = Math.max(1, parseInt(count, 10) || 1);
    container.innerHTML = "";
    for (let i = 1; i <= count; i++) {
        container.appendChild(createColorOption(group, i));
    }
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
}

function ensureAllColorGroups(settings) {
    Object.values(COLOR_GROUPS).forEach((group) => {
        const count = settings && settings[group.countId];
        ensureColorGroup(group, count);
    });
}

function initColorGroups() {
    Object.values(COLOR_GROUPS).forEach((group) => {
        updateColorButtons(group);
    });
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
    // Sample from bar color inputs: bar_color, bar_color_2, bar_color_3, ...
    // Falls back to fish_color then arrow_color if no valid bar colors exist.
    const barColors = [];
    const first = document.getElementById("bar_color");
    if (first) barColors.push(first);
    
    // Find any additional bar color inputs (bar_color_2, bar_color_3, ...)
    let i = 2;
    while (true) {
        const el = document.getElementById(`bar_color_${i}`);
        if (!el) break;
        barColors.push(el);
        i++;
    }

    const getVal = (el) => el ? (el.value || el.placeholder || "").trim() : "";
    const fishElement = document.getElementById("fish_color");
    const arrowElement = document.getElementById("arrow_color");

    const normalizedBar = barColors
        .map(el => normalizeHexColor(getVal(el)))
        .filter(Boolean);
    const normalizedFish = normalizeHexColor(getVal(fishElement));
    const normalizedArrow = normalizeHexColor(getVal(arrowElement));

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

    // Filter to only "usable" bar colors
    const usable = normalizedBar.filter(hex => !isTooNeutral(hex));

    let leftGradient = "#fa6b35";
    let rightGradient = "#fa6b35";
    let accentColor = "#fa6b35";
    let isGradient = false;

    if (usable.length >= 2) {
        // Two or more usable bar colors → gradient using first two
        leftGradient = usable[0];
        rightGradient = usable[1];
        accentColor = usable[0];
        isGradient = true;
    } else if (usable.length === 1) {
        // Only one usable bar color → static
        leftGradient = usable[0];
        rightGradient = usable[0];
        accentColor = usable[0];
    } else if (!isTooNeutral(normalizedFish)) {
        // Fallback to fish color
        leftGradient = normalizedFish;
        rightGradient = normalizedFish;
        accentColor = normalizedFish;
    } else if (!isTooNeutral(normalizedArrow)) {
        // Fallback to arrow color
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
    const glowBase = isGradient ? leftGradient : accentColor;
    const r = parseInt(glowBase.substr(1, 2), 16);
    const g = parseInt(glowBase.substr(3, 2), 16);
    const b = parseInt(glowBase.substr(5, 2), 16);
    document.documentElement.style.setProperty("--accent-glow", `rgba(${r}, ${g}, ${b}, 0.4)`);
    document.documentElement.style.setProperty("--focus-glow", `rgba(${r}, ${g}, ${b}, 0.28)`);
    document.documentElement.style.setProperty("--focus-ring", `rgba(${r}, ${g}, ${b}, 0.75)`);
    document.documentElement.style.setProperty("--border-soft", `rgba(${r}, ${g}, ${b}, 0.3)`);
    document.documentElement.style.setProperty("--border-medium", `rgba(${r}, ${g}, ${b}, 0.25)`);
    document.documentElement.style.setProperty("--border-strong", `rgba(${r}, ${g}, ${b}, 0.35)`);
    document.documentElement.style.setProperty("--scrollbar-thumb", accentColor);
    document.documentElement.style.setProperty("--scrollbar-thumb-hover", rightGradient);

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

let _bannerConfirmHandler = null;
let _bannerCancelHandler = null;

function hideBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.add("hidden");
    _bannerConfirmHandler = null;
    _bannerCancelHandler = null;
}

function showBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.remove("hidden");
}

function showUpdateBanner(options = {}) {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const actions = document.getElementById("banner-actions");

    const titleText = options.title || "Update Available";
    const noticeText = options.notice || "A new version of Solar Fishing is available. Choose an option below.";

    if (title) title.textContent = titleText;
    if (notice) notice.textContent = noticeText;
    if (dialogue) dialogue.classList.add("hidden");

    _bannerConfirmHandler = options.onConfirm || null;
    _bannerCancelHandler = options.onCancel || null;

    if (actions) {
        if (options.buttons && Array.isArray(options.buttons)) {
            actions.innerHTML = options.buttons.map((btn, i) => {
                const cls = btn.class || "btn-secondary";
                const label = btn.label || "OK";
                return `<button type="button" class="${cls}" data-banner-btn="${i}">${label}</button>`;
            }).join("");
            actions.querySelectorAll("[data-banner-btn]").forEach((el) => {
                const idx = Number(el.getAttribute("data-banner-btn"));
                const btn = options.buttons[idx];
                el.addEventListener("click", () => {
                    if (typeof btn.onClick === "function") {
                        btn.onClick();
                    }
                    hideBanner();
                });
            });
        } else {
            actions.innerHTML = `
                <button type="button" class="btn-ghost" id="banner-cancel-btn">Cancel</button>
                <button type="button" class="btn-primary" id="banner-confirm-btn">Confirm</button>
            `;
            const cancelBtn = document.getElementById("banner-cancel-btn");
            const confirmBtn = document.getElementById("banner-confirm-btn");
            if (cancelBtn) {
                cancelBtn.addEventListener("click", () => {
                    if (typeof _bannerCancelHandler === "function") _bannerCancelHandler();
                    hideBanner();
                });
            }
            if (confirmBtn) {
                confirmBtn.addEventListener("click", () => {
                    if (typeof _bannerConfirmHandler === "function") _bannerConfirmHandler();
                    hideBanner();
                });
            }
        }
    }

    showBanner();
}

function showDialogueBanner(options = {}) {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const input = document.getElementById("banner-input");
    const actions = document.getElementById("banner-actions");

    const titleText = options.title || "Dialogue";
    const noticeText = options.notice || "Enter a value and confirm.";
    const placeholder = options.placeholder || "Enter a value...";

    if (title) title.textContent = titleText;
    if (notice) notice.textContent = noticeText;
    if (dialogue) dialogue.classList.remove("hidden");
    if (input) {
        input.value = options.value || "";
        input.placeholder = placeholder;
        setTimeout(() => input.focus(), 50);
    }

    _bannerConfirmHandler = options.onConfirm || null;
    _bannerCancelHandler = options.onCancel || null;

    if (actions) {
        actions.innerHTML = `
            <button type="button" class="btn-ghost" id="banner-cancel-btn">Cancel</button>
            <button type="button" class="btn-primary" id="banner-confirm-btn">Confirm</button>
        `;
        const cancelBtn = document.getElementById("banner-cancel-btn");
        const confirmBtn = document.getElementById("banner-confirm-btn");
        if (cancelBtn) {
            cancelBtn.addEventListener("click", () => {
                if (typeof _bannerCancelHandler === "function") _bannerCancelHandler();
                hideBanner();
            });
        }
        if (confirmBtn) {
            confirmBtn.addEventListener("click", () => {
                const value = input ? input.value.trim() : "";
                if (typeof _bannerConfirmHandler === "function") {
                    _bannerConfirmHandler(value);
                }
                hideBanner();
            });
        }
    }

    showBanner();
}

function confirmDialogue() {
    const input = document.getElementById("banner-input");
    const value = input ? input.value.trim() : "";
    if (typeof _bannerConfirmHandler === "function") {
        _bannerConfirmHandler(value);
    }
    hideBanner();
}

/**
 * Custom bottom-banner replacement for window.alert / window.confirm.
 * Returns a Promise that resolves to true/false (askyesno) or null (ok).
 * Called from Python via evaluate_js; result is delivered by calling
 * pywebview.api.message_box_result(...).
 */
function showMessageBoxBanner(message, type = "ok") {
    const safeMessage = String(message || "").replace(/\\n/g, "\n");
    const title = type === "askyesno" ? "Confirm" : "Notice";

    return new Promise((resolve) => {
        const finish = (value) => {
            resolve(value);
            try {
                if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.message_box_result === "function") {
                    window.pywebview.api.message_box_result(value);
                }
            } catch (e) {
                console.error(e);
            }
        };

        if (type === "askyesno") {
            showUpdateBanner({
                title: title,
                notice: safeMessage,
                buttons: [
                    { label: "No", class: "btn-ghost", onClick: () => finish(false) },
                    { label: "Yes", class: "btn-primary", onClick: () => finish(true) }
                ]
            });
        } else {
            showUpdateBanner({
                title: title,
                notice: safeMessage,
                buttons: [
                    { label: "OK", class: "btn-primary", onClick: () => finish(null) }
                ]
            });
        }
    });
}

/* =========================
   CONFIG / ROD ACTIONS
   ========================= */

function isColorSetting(key) {
    if (!key) return false;
    const k = String(key).toLowerCase();
    return k.includes("color") || k.includes("tolerance");
}

async function RefreshConfigs() {
    const preferred = selectedConfigName();
    const configs = await refreshConfigs(preferred);
    setStatus("Configs refreshed" + (configs && configs.length ? ` (${configs.length})` : ""));
}

async function AddRod() {
    // Save current settings first
    try {
        await saveSettings();
    } catch (error) {
        console.error(error);
    }

    showDialogueBanner({
        title: "Add Rod",
        notice: "Enter a name for the new rod configuration.",
        placeholder: "Rod name...",
        onConfirm: async (name) => {
            name = String(name || "").trim();
            if (!name) {
                showUpdateBanner({
                    title: "Invalid Name",
                    notice: "Please enter a non-empty rod name.",
                    buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                });
                return;
            }
            // Basic safety
            if (/[\\/:*?"<>|]/.test(name)) {
                showUpdateBanner({
                    title: "Invalid Name",
                    notice: "Rod name contains invalid characters.",
                    buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                });
                return;
            }

            const api = _pyApi();
            if (!api || typeof api.list_configs !== "function") {
                return;
            }

            let existing = [];
            try {
                existing = await api.list_configs();
            } catch (e) {
                existing = [];
            }
            if (Array.isArray(existing) && existing.some(c => String(c).toLowerCase() === name.toLowerCase())) {
                showUpdateBanner({
                    title: "Name Exists",
                    notice: `A configuration named "${name}" already exists.`,
                    buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                });
                return;
            }

            // Create by saving current settings under the new name
            try {
                await saveSettings(name);
                await refreshConfigs(name);
                currentConfig = name;
                setStatus("Added rod: " + name);
            } catch (error) {
                console.error(error);
                showUpdateBanner({
                    title: "Error",
                    notice: "Failed to create the new rod configuration.",
                    buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                });
            }
        }
    });
}

async function DeleteRod() {
    const name = selectedConfigName();
    if (!name) {
        return;
    }
    if (name.toLowerCase() === "default") {
        showUpdateBanner({
            title: "Cannot Delete",
            notice: "The Default configuration cannot be deleted.",
            buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
        });
        return;
    }

    showUpdateBanner({
        title: "Delete Rod",
        notice: `Are you sure you want to delete the configuration "${name}"? This cannot be undone.`,
        buttons: [
            { label: "Cancel", class: "btn-ghost", onClick: () => {} },
            {
                label: "Delete",
                class: "btn-primary",
                onClick: async () => {
                    const api = _pyApi();
                    if (!api || typeof api.delete_config !== "function") {
                        return;
                    }
                    try {
                        const result = await api.delete_config(name);
                        if (result && result.success) {
                            const configs = await refreshConfigs();
                            const next = configs && configs.length ? configs[0] : "Default";
                            await loadSettings(next);
                            setStatus("Deleted rod: " + name);
                        } else {
                            showUpdateBanner({
                                title: "Error",
                                notice: (result && result.error) || "Failed to delete configuration.",
                                buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                            });
                        }
                    } catch (error) {
                        console.error(error);
                        showUpdateBanner({
                            title: "Error",
                            notice: "Failed to delete configuration.",
                            buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                        });
                    }
                }
            }
        ]
    });
}

async function ResetSettings() {
    const name = selectedConfigName();
    showUpdateBanner({
        title: "Reset Settings",
        notice: `Reset all settings for "${name}" to defaults? Colors will be kept.`,
        buttons: [
            { label: "Cancel", class: "btn-ghost", onClick: () => {} },
            {
                label: "Reset",
                class: "btn-primary",
                onClick: async () => {
                    try {
                        // Preserve current color-related settings
                        const current = collectSettings();
                        const colorSettings = {};
                        Object.entries(current).forEach(([key, value]) => {
                            if (isColorSetting(key)) {
                                colorSettings[key] = value;
                            }
                        });

                        // Reset everything to HTML defaults
                        resetFieldsToDefaults();

                        // Re-apply preserved colors
                        if (Object.keys(colorSettings).length) {
                            applySettings(colorSettings, false);
                        }

                        // Make sure color groups rebuild correctly
                        if (typeof ensureAllColorGroups === "function") {
                            ensureAllColorGroups(collectSettings());
                        }
                        if (typeof updateColorPreviews === "function") {
                            updateColorPreviews();
                        }
                        if (typeof updateAccentColor === "function") {
                            updateAccentColor();
                        }

                        await saveSettings(name);
                        setStatus("Settings reset (colors kept): " + name);
                    } catch (error) {
                        console.error(error);
                        showUpdateBanner({
                            title: "Error",
                            notice: "Failed to reset settings.",
                            buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                        });
                    }
                }
            }
        ]
    });
}

async function OpenFolder() {
    const api = _pyApi();
    if (!api || typeof api.open_base_folder !== "function") {
        setStatus("Open folder unavailable");
        return;
    }
    try {
        const result = await api.open_base_folder();
        if (result && result.success) {
            setStatus("Opened configs folder");
        } else {
            showUpdateBanner({
                title: "Open Folder",
                notice: (result && result.error) || "Could not open the folder.",
                buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
            });
        }
    } catch (error) {
        console.error(error);
        showUpdateBanner({
            title: "Open Folder",
            notice: "Could not open the folder.",
            buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
        });
    }
}

function _suggestConfigNameFromFile(filename) {
    let name = String(filename || "").trim();
    if (name.toLowerCase().endsWith(".json")) {
        name = name.slice(0, -5);
    }
    name = name.replace(/[\\/:*?"<>|]/g, "").trim();
    return name || "Imported";
}

async function ImportConfigs() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.style.display = "none";
    document.body.appendChild(input);

    input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        document.body.removeChild(input);
        if (!file) {
            return;
        }

        let text = "";
        try {
            text = await file.text();
        } catch (error) {
            showUpdateBanner({
                title: "Import Failed",
                notice: "Could not read the selected file.",
                buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
            });
            return;
        }

        let settings = null;
        try {
            settings = JSON.parse(text);
        } catch (error) {
            showUpdateBanner({
                title: "Import Failed",
                notice: "The file is not valid JSON.",
                buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
            });
            return;
        }

        if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
            showUpdateBanner({
                title: "Import Failed",
                notice: "Config file must contain a JSON object.",
                buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
            });
            return;
        }

        const suggested = _suggestConfigNameFromFile(file.name);

        showDialogueBanner({
            title: "Import Config",
            notice: "Choose a name for the imported configuration.",
            placeholder: "Config name...",
            value: suggested,
            onConfirm: async (name) => {
                name = String(name || "").trim();
                if (!name) {
                    showUpdateBanner({
                        title: "Invalid Name",
                        notice: "Please enter a non-empty config name.",
                        buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                    });
                    return;
                }
                if (/[\\/:*?"<>|]/.test(name)) {
                    showUpdateBanner({
                        title: "Invalid Name",
                        notice: "Config name contains invalid characters.",
                        buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                    });
                    return;
                }

                const api = _pyApi();
                if (!api || typeof api.save_settings !== "function") {
                    return;
                }

                let existing = [];
                try {
                    if (typeof api.list_configs === "function") {
                        existing = await api.list_configs();
                    }
                } catch (e) {
                    existing = [];
                }
                if (Array.isArray(existing) && existing.some(c => String(c).toLowerCase() === name.toLowerCase())) {
                    showUpdateBanner({
                        title: "Name Exists",
                        notice: `A configuration named "${name}" already exists.`,
                        buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                    });
                    return;
                }

                try {
                    const result = await api.save_settings(name, settings);
                    if (result && result.success === false) {
                        showUpdateBanner({
                            title: "Import Failed",
                            notice: result.error || "Could not save the imported config.",
                            buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                        });
                        return;
                    }
                    await refreshConfigs(name);
                    currentConfig = name;
                    await loadSettings(name);
                    setStatus("Imported: " + name);
                } catch (error) {
                    console.error(error);
                    showUpdateBanner({
                        title: "Import Failed",
                        notice: "Could not save the imported config.",
                        buttons: [{ label: "OK", class: "btn-primary", onClick: () => {} }]
                    });
                }
            }
        });
    }, { once: true });

    input.click();
}

async function ExportConfigs() {
    const name = selectedConfigName() || "config";
    let settings = {};
    try {
        settings = collectSettingsData();
    } catch (error) {
        settings = collectSettings();
    }

    const safeName = String(name).replace(/[\\/:*?"<>|]/g, "").trim() || "config";
    const filename = safeName + ".json";
    const json = JSON.stringify(settings, null, 4);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);

    setStatus("Exported: " + filename);
}
