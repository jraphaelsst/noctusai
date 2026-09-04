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
    },
    update: (state, action: PayloadAction<{ index: number; item: Interesse }>) => {
      const { index, item } = action.payload
      if (index >= 0 && index < state.items.length) {
        state.items[index] = item
      }
    },
    remove: (state, action: PayloadAction<number>) => {
      const index = action.payload
      if (index >= 0 && index < state.items.length) {
        state.items.splice(index, 1)
      }
    }
  }
})

export const { openInteresses, closeInteresses, add, update, remove } = overlaySlice.actions

export default overlaySlice.reducer
