import { useDispatch, useSelector } from 'react-redux'

import { RootReducer } from '../../store'
import { closeProp } from '../../store/reducers/overlayProprietario'

import { FormContainer, Overlay, OverlayContainer, Title } from './styles'

type Props = {
  title: string
  children: JSX.Element[]
}

const OverlayPropForm = ({ title, children }: Props) => {
  const { isPropOpen } = useSelector((state: RootReducer) => state.overlayProp)

  const dispatch = useDispatch()
  const closeForm = () => {
    dispatch(closeProp())
  }

  return (
    <OverlayContainer className={isPropOpen ? 'isOpen' : ''}>
      <FormContainer>
        <Title>{title}</Title>
        {children}
      </FormContainer>
      <Overlay onClick={closeForm} />
    </OverlayContainer>
  )
}

export default OverlayPropForm
