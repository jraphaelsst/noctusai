import { createSlice } from '@reduxjs/toolkit'

type OverlayState = {
  isPropOpen: boolean
}

const initialState: OverlayState = {
  isPropOpen: false
}

const overlaySlice = createSlice({
  name: 'overlayProprietario',
  initialState,
  reducers: {
    openProp: (state) => {
      state.isPropOpen = true
    },
    closeProp: (state) => {
      state.isPropOpen = false
    }
  }
})

export const { openProp, closeProp } = overlaySlice.actions
export default overlaySlice.reducer
