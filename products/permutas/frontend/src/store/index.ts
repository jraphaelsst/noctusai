import { configureStore } from '@reduxjs/toolkit'

import overlayPropReducer from './reducers/overlayProprietario'
import overlayCondoReducer from './reducers/overlayCondominio'
import overlayInteressesReducer from './reducers/overlayInteresses'

import api from '../services/api'

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    overlayProp: overlayPropReducer,
    overlayCondo: overlayCondoReducer,
    overlayInteresses: overlayInteressesReducer
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(api.middleware)
})

export type RootReducer = ReturnType<typeof store.getState>
