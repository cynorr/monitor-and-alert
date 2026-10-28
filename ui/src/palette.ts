// Shared semantic colors. CSS receives the same values through installPalette().
export const palette = {
    blue: '#2962ff', blueSoft: '#e8f1ff', yellow: '#e4b400', yellowText: '#b89100', yellowSoft: '#fff3c4',
    red: '#e53935', redStrong: '#b42318', positive: '#008f83', negative: '#df4543',
    candleUp: '#26a69a', candleDown: '#ef5350', tagNeutral: '#64748b',
    volumeBase: '#f4f5f7', volumeLow: '#e5e7eb', volumeMedium: '#cbd2db', volumeHigh: '#374151',
    ink: '#000000', white: '#ffffff', muted: '#9ca3af',
} as const;

export function installPalette() {
    for (const [name, value] of Object.entries(palette))
        document.documentElement.style.setProperty('--color-' + name.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase()), value);
}
