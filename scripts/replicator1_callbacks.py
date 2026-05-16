# replicator1_callbacks
# Callback del Replicator COMP de tiles.
# table_tilelist solo tiene filas para tiles REALES (con imagen en disco).
# El replicador crea exactamente un op por fila -> no hay gaps.
# Aqui asignamos archivos Y cableamos el switch compacto.


def onRemoveReplicant(comp, replicant):
	return


def onReplicate(comp, allOps, newOps, template, master):
	dat = op('table_tilelist')
	sw  = op('switch_tiles')

	# Lookup id -> filePath
	id_to_file = {}
	for r in range(1, dat.numRows):
		try:
			id_to_file[int(dat[r, 'id'])] = str(dat[r, 'filePath'])
		except:
			pass

	# Asignar archivo a cada op replicado
	for tile_op in allOps:
		tile_op.par.file = id_to_file.get(tile_op.digits, '')

	# Cablear switch compacto: ordenar por row_major_id (digits)
	# input[0] = tile con id mas bajo, input[1] = siguiente, etc.
	# El shader usa uIds para saber que id corresponde a cada capa.
	if sw is not None:
		sorted_ops = sorted(allOps, key=lambda o: o.digits if o.digits is not None else 0)
		sw.setInputs(sorted_ops)

	return
