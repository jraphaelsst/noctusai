import { createSlice } from '@reduxjs/toolkit'

type OverlayState = {
  isCondoOpen: boolean
}

const initialState: OverlayState = {
  isCondoOpen: false
}

const overlaySlice = createSlice({
  name: 'overlayCondominio',
  initialState,
  reducers: {
    openCondo: (state) => {
      state.isCondoOpen = true
    },
    closeCondo: (state) => {
      state.isCondoOpen = false
    }
  }
})

export const { openCondo, closeCondo } = overlaySlice.actions
export default overlaySlice.reducer
