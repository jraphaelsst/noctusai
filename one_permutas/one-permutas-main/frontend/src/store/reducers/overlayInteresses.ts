import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export type Interesse = {
  tipo: string
  tipo_imovel?: string
  estado?: string
  zona?: string
  tipo_automovel?: string
  valor_minimo: number
  valor_maximo: number
}

type OverlayState = {
  items: Interesse[]
  isInteressesOpen: boolean
}

const initialState: OverlayState = {
  items: [],
  isInteressesOpen: false
}

const overlaySlice = createSlice({
  name: 'overlayInteresses',
  initialState,
  reducers: {
    openInteresses: (state) => {
      state.isInteressesOpen = true
    },
    closeInteresses: (state) => {
      state.isInteressesOpen = false
    },
    add: (state, action: PayloadAction<Interesse>) => {
      state.items.push(action.payload)
    }
  }
})

export const { openInteresses, closeInteresses, add } = overlaySlice.actions

export default overlaySlice.reducer
