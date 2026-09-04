import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

import { ClienteType } from '../pages/Clientes'
import { CondominioType } from '../pages/Condominios'
import { ImovelType } from '../pages/Imoveis'
import { PermutaImovelType, PermutaAutomovelType } from '../pages/Permutas'

const getBaseUrl = () => {
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL
  }
  return ''
}

const api = createApi({
  baseQuery: fetchBaseQuery({
    baseUrl: getBaseUrl(),
    prepareHeaders: (headers) => {
      const tokensStr = localStorage.getItem('authTokens')
      if (tokensStr) {
        try {
          const tokens = JSON.parse(tokensStr)
          if (tokens?.access) {
            headers.set('Authorization', `Bearer ${tokens.access}`)
          }
        } catch (e) {
          console.error('Failed to parse auth tokens')
        }
      }
      return headers
    }
  }),
  keepUnusedDataFor: 300,
  refetchOnMountOrArgChange: 300,
  tagTypes: ['Clientes', 'Condominios', 'Imoveis', 'Permutas', 'Corretores', 'Tipos', 'Zonas', 'Matches', 'TiposImovel', 'TiposAutomovel'],
  endpoints: (builder) => ({
    getClientes: builder.query<ClienteType[], void>({
      query: () => 'proprietario/',
      providesTags: ['Clientes']
    }),
    getCliente: builder.query<ClienteType, void>({
      query: (id) => `proprietario/${id}/`,
      providesTags: ['Clientes']
    }),
    getCondominios: builder.query<CondominioType[], void>({
      query: () => 'condominio/',
      providesTags: ['Condominios']
    }),
    getCondominio: builder.query<CondominioType, void>({
      query: (id) => `condominio/${id}/`,
      providesTags: ['Condominios']
    }),
    getImoveis: builder.query<ImovelType[], void>({
      query: () => 'imovel/',
      providesTags: ['Imoveis']
    }),
    getImovel: builder.query<ImovelType, string>({
      query: (id) => `imovel/${id}/`,
      providesTags: ['Imoveis']
    }),
    getPermutasImovel: builder.query<PermutaImovelType[], void>({
      query: () => 'permuta/imovel/',
      providesTags: ['Permutas']
    }),
    getPermutaImovel: builder.query<PermutaImovelType, string>({
      query: (id) => `permuta/imovel/${id}/`,
      providesTags: ['Permutas']
    }),
    getPermutasAutomovel: builder.query<PermutaAutomovelType[], void>({
      query: () => 'permuta/automovel/',
      providesTags: ['Permutas']
    }),
    getPermutaAutomovel: builder.query<PermutaAutomovelType, string>({
      query: (id) => `permuta/automovel/${id}/`,
      providesTags: ['Permutas']
    }),
    postNovoImovel: builder.mutation<unknown, ImovelType>({
      query: (body) => ({
        url: 'imovel/',
        method: 'POST',
        body
      }),
      invalidatesTags: ['Imoveis', 'Matches']
    }),
    postNovoCondominio: builder.mutation<unknown, CondominioType>({
      query: (body) => ({
        url: 'condominio/',
        method: 'POST',
        body
      }),
      invalidatesTags: ['Condominios']
    }),
    postNovaPermutaImovel: builder.mutation<unknown, PermutaImovelType>({
      query: (body) => ({
        url: 'permuta/imovel/',
        method: 'POST',
        body
      }),
      invalidatesTags: ['Permutas', 'Matches']
    }),
    postNovaPermutaAutomovel: builder.mutation<unknown, PermutaAutomovelType>({
      query: (body) => ({
        url: 'permuta/automovel/',
        method: 'POST',
        body
      }),
      invalidatesTags: ['Permutas', 'Matches']
    }),
    postNovoCliente: builder.mutation<unknown, ClienteType>({
      query: (body) => ({
        url: 'proprietario/',
        method: 'POST',
        body
      }),
      invalidatesTags: ['Clientes']
    })
  })
})

export const {
  useGetClientesQuery,
  useGetClienteQuery,
  useGetCondominiosQuery,
  useGetCondominioQuery,
  useGetImoveisQuery,
  useGetImovelQuery,
  useGetPermutasImovelQuery,
  useGetPermutaImovelQuery,
  useGetPermutasAutomovelQuery,
  useGetPermutaAutomovelQuery,
  usePostNovoImovelMutation,
  usePostNovoCondominioMutation,
  usePostNovaPermutaImovelMutation,
  usePostNovaPermutaAutomovelMutation,
  usePostNovoClienteMutation
} = api

export default api
