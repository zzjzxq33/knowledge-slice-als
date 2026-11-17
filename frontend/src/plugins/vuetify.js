import { createVuetify } from 'vuetify'
import { zhHans } from 'vuetify/locale'

const light = {
  dark: false,
  colors: {
    background: '#F4F5FA',
    surface: '#FFFFFF',
    primary: '#4F46E5',
    secondary: '#0D9488',
    error: '#DC2626',
    info: '#0284C7',
    success: '#16A34A',
    warning: '#D97706',
  },
}

const dark = {
  dark: true,
  colors: {
    background: '#0F1117',
    surface: '#171A23',
    primary: '#818CF8',
    secondary: '#2DD4BF',
    error: '#F87171',
    info: '#38BDF8',
    success: '#4ADE80',
    warning: '#FBBF24',
  },
}

export default createVuetify({
  locale: {
    locale: 'zhHans',
    fallback: 'zhHans',
    messages: { zhHans },
  },
  theme: {
    defaultTheme: 'light',
    themes: { light, dark },
  },
  defaults: {
    VCard: { rounded: 'xl' },
    VBtn: { rounded: 'lg' },
    VTextField: { variant: 'outlined', density: 'comfortable' },
    VSelect: { variant: 'outlined', density: 'comfortable' },
    VTextarea: { variant: 'outlined', density: 'comfortable' },
    VChip: { rounded: 'lg' },
    VAlert: { rounded: 'lg' },
  },
})
