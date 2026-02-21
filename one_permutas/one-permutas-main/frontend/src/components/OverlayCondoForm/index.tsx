import { useDispatch, useSelector } from 'react-redux'

import { RootReducer } from '../../store'
import { closeCondo } from '../../store/reducers/overlayCondominio'

import { FormContainer, Overlay, OverlayContainer, Title } from './styles'

type Props = {
  title: string
  children: JSX.Element[]
}

const OverlayCondoForm = ({ title, children }: Props) => {
  const { isCondoOpen } = useSelector(
    (state: RootReducer) => state.overlayCondo
  )

  const dispatch = useDispatch()
  const closeForm = () => {
    dispatch(closeCondo())
  }

  return (
    <OverlayContainer className={isCondoOpen ? 'isOpen' : ''}>
      <FormContainer>
        <Title>{title}</Title>
        {children}
      </FormContainer>
      <Overlay onClick={closeForm} />
    </OverlayContainer>
  )
}

export default OverlayCondoForm
