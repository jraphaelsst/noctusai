import { styled } from 'styled-components'

import { breakpoints } from '../../styles'

export const FormContainer = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  height: 100vh;
  width: 90%;
  margin: 0 auto;
  align-items: center;
  justify-items: center;

  img {
    width: 100%;
  }

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`
